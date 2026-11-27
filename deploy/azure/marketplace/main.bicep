// CosmosProof as an Azure Marketplace Managed Application (ADR 0003, ADR 0007).
//
// Deploys into the managed resource group, in the customer's subscription: a user-assigned
// managed identity, a Log Analytics workspace for the scanner output, a storage account for
// published runs (the only place CosmosProof writes) and a daily Container Apps Job.
// The daily job runs `cosmosproof audit`: discovery over the chosen scope, the selection made
// in the app, and cosmosproof.audit with its Parquet model (ADR 0010). Access to the
// customer's resources is granted by the customer; the app shows what is missing.
//
// Compile to mainTemplate.json with: az bicep build --file main.bicep --outfile mainTemplate.json

@description('Location for all resources.')
param location string = resourceGroup().location

@description('Discovery scope: subscriptions or managementGroups.')
@allowed([ 'subscriptions', 'managementGroups' ])
param scopeType string = 'subscriptions'

@description('Comma-separated subscription IDs or management group IDs to discover. The identity needs Reader on them.')
param scopeIds string

@description('No read in this many days means unused.')
@minValue(1)
@maxValue(395)
param windowDays int = 90

@description('Date last access time tracking was enabled on the ADLS accounts (yyyy-mm-dd), or empty if it is off.')
param accessTrackingSince string = ''

@description('Daily audit time, as a cron expression in UTC.')
param cron string = '0 6 * * *'

@description('Scanner image. Fixed by the publisher.')
param image string = 'ghcr.io/wiliamrosa/cosmosproof:0.1.0'

@description('Customer usage attribution ID assigned by Partner Center. Empty outside the Marketplace.')
param partnerCenterPid string = ''

var suffix = uniqueString(resourceGroup().id)
var reportsAccountName = take('cpreports${suffix}', 24)
var reportsContainer = 'cosmosproof-reports'
var scopeKey = scopeType == 'subscriptions' ? 'subscriptions' : 'management_groups'
var trackingBlock = empty(accessTrackingSince) ? '' : 'storage:\n  access_tracking_since: ${accessTrackingSince}\n'
var auditConfig = format(
  '''location: abfss://{0}@{1}.dfs.{2}/audit
discovery:
  {3}: [{4}]
window_days: {5}
{6}''',
  reportsContainer,
  reportsAccountName,
  environment().suffixes.storage,
  scopeKey,
  scopeIds,
  windowDays,
  trackingBlock
)

// Partner Center customer usage attribution: a no-op deployment named after the offer's ID.
resource attribution 'Microsoft.Resources/deployments@2021-04-01' = if (!empty(partnerCenterPid)) {
  name: 'pid-${partnerCenterPid}-partnercenter'
  properties: {
    mode: 'Incremental'
    template: {
      '$schema': 'https://schema.management.azure.com/schemas/2019-04-01/deploymentTemplate.json#'
      contentVersion: '1.0.0.0'
      resources: []
    }
  }
}

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'cosmosproof-identity'
  location: location
}

resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'cosmosproof-logs-${suffix}'
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

resource reports 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: reportsAccountName
  location: location
  kind: 'StorageV2'
  sku: {
    name: 'Standard_LRS'
  }
  properties: {
    isHnsEnabled: true
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    allowSharedKeyAccess: false
    supportsHttpsTrafficOnly: true
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: reports
  name: 'default'
}

resource reportsContainerResource 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: reportsContainer
}

// Storage Blob Data Contributor on the reports container only: everywhere else the identity
// stays read-only.
resource reportsWriter 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(reportsContainerResource.id, identity.id, 'Storage Blob Data Contributor')
  scope: reportsContainerResource
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
    )
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource env 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: 'cosmosproof-env'
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logs.properties.customerId
        sharedKey: logs.listKeys().primarySharedKey
      }
    }
  }
}

resource job 'Microsoft.App/jobs@2024-03-01' = {
  name: 'cosmosproof-scan'
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${identity.id}': {}
    }
  }
  properties: {
    environmentId: env.id
    configuration: {
      triggerType: 'Schedule'
      replicaTimeout: 1800
      replicaRetryLimit: 1
      scheduleTriggerConfig: {
        cronExpression: cron
        parallelism: 1
        replicaCompletionCount: 1
      }
      secrets: [
        {
          name: 'scan-config'
          value: auditConfig
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'scanner'
          image: image
          args: [ 'audit' ]
          env: [
            { name: 'COSMOSPROOF_CONFIG', secretRef: 'scan-config' }
            { name: 'AZURE_CLIENT_ID', value: identity.properties.clientId }
          ]
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
        }
      ]
    }
  }
  dependsOn: [ reportsWriter ]
}

@description('Application (client) ID of the CosmosProof identity: add it to Databricks as a service principal.')
output identityClientId string = identity.properties.clientId

@description('Object (principal) ID of the CosmosProof identity, for Azure role assignments.')
output identityPrincipalId string = identity.properties.principalId

@description('Where cosmosproof.audit, the selection and the Parquet model live.')
output auditLocation string = 'abfss://${reportsContainer}@${reportsAccountName}.dfs.${environment().suffixes.storage}/audit'

@description('Next steps: grant Reader on the discovery scope, then install the app in a home workspace.')
output nextSteps string = 'Grant Reader to object ${identity.properties.principalId} on: ${scopeIds}. Then a Databricks workspace administrator runs app/deploy.py with --identity-app-id ${identity.properties.clientId}.'
