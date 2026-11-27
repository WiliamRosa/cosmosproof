// CosmosProof as an Azure Marketplace Managed Application (ADR 0003, ADR 0007).
//
// Deploys into the managed resource group, in the customer's subscription: a user-assigned
// managed identity, a Log Analytics workspace for the scanner output, a storage account for
// published runs (the only place CosmosProof writes) and a daily Container Apps Job.
// Access to the customer's Databricks and ADLS is granted by the customer after deployment,
// with the commands `cosmosproof grants` prints for the identity in the outputs.
//
// Compile to mainTemplate.json with: az bicep build --file main.bicep --outfile mainTemplate.json

@description('Location for all resources.')
param location string = resourceGroup().location

@description('Azure Databricks workspace host, e.g. adb-1234567890123456.7.azuredatabricks.net.')
param databricksHost string

@description('ID of the SQL warehouse CosmosProof queries.')
param warehouseId string

@description('ADLS Gen2 account to scan.')
param storageAccountName string

@description('Container to scan in that account.')
param storageContainer string

@description('No read in this many days means unused.')
@minValue(1)
@maxValue(395)
param windowDays int = 90

@description('Date last access time tracking was enabled on the account (yyyy-mm-dd), or empty if it is off.')
param accessTrackingSince string = ''

@description('Daily scan time, as a cron expression in UTC.')
param cron string = '0 6 * * *'

@description('Scanner image. Fixed by the publisher.')
param image string = 'ghcr.io/wiliamrosa/cosmosproof:0.1.0'

@description('Customer usage attribution ID assigned by Partner Center. Empty outside the Marketplace.')
param partnerCenterPid string = ''

var suffix = uniqueString(resourceGroup().id)
var reportsAccountName = take('cpreports${suffix}', 24)
var reportsContainer = 'cosmosproof-reports'
var trackingLine = empty(accessTrackingSince) ? '' : '\n    access_tracking_since: ${accessTrackingSince}'
var scanConfig = format(
  '''window_days: {0}
databricks:
  source:
    type: databricks
    max_rows: 1000000
    timeout_seconds: 600
    options:
      server_hostname: {1}
      http_path: /sql/1.0/warehouses/{2}
      auth: azure
storage:
  - account: {3}
    container: {4}
    list_directly: true{5}
publish: abfss://{6}@{7}.dfs.{8}/runs
''',
  windowDays,
  databricksHost,
  warehouseId,
  storageAccountName,
  storageContainer,
  trackingLine,
  reportsContainer,
  reportsAccountName,
  environment().suffixes.storage
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
          value: scanConfig
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'scanner'
          image: image
          args: [ 'scan', '--markdown', '/tmp/report.md' ]
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

@description('Where each run is published.')
output publishLocation string = 'abfss://${reportsContainer}@${reportsAccountName}.dfs.${environment().suffixes.storage}/runs'

@description('Print the grants to give, for a person to review and run.')
output grantsCommand string = 'cosmosproof grants --application-id ${identity.properties.clientId} --object-id ${identity.properties.principalId} --subscription ${subscription().subscriptionId} --storage <resource-group>/${storageAccountName} --catalog <catalog>'
