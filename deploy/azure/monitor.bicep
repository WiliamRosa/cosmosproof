// Scheduled CosmosProof scan: an Azure Container Apps Job running the scanner image with a
// user-assigned managed identity (ADR 0007). No secret is stored except the scan
// configuration, which holds no credential: Databricks and storage are reached with the
// identity's Entra ID tokens.

@description('Location for all resources.')
param location string = resourceGroup().location

@description('Name prefix for the resources.')
param namePrefix string = 'cosmosproof'

@description('Existing user-assigned managed identity CosmosProof runs as.')
param identityName string

@description('Container registry login server, e.g. myacr.azurecr.io. The identity needs AcrPull on it.')
param registryServer string

@description('Scanner image, e.g. myacr.azurecr.io/cosmosproof:0.1.')
param image string

@description('Cron expression (UTC) for the scan.')
param cron string = '0 10 * * *'

@description('Scanner command: audit (estate-wide, ADR 0010) or scan (one configured workspace).')
param args array = [ 'audit' ]

@secure()
@description('cosmosproof.yml content. Use `auth: azure` for Databricks and `list_directly` for storage, so it holds no credential.')
param scanConfig string

@description('Keep the scanner output in a Log Analytics workspace (30 days), so every run can be audited.')
param enableLogs bool = true

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' existing = {
  name: identityName
}

resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = if (enableLogs) {
  name: '${namePrefix}-logs'
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

resource env 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: '${namePrefix}-env'
  location: location
  properties: enableLogs
    ? {
        appLogsConfiguration: {
          destination: 'log-analytics'
          logAnalyticsConfiguration: {
            customerId: logs.properties.customerId
            sharedKey: logs.listKeys().primarySharedKey
          }
        }
      }
    : {}
}

resource job 'Microsoft.App/jobs@2024-03-01' = {
  name: '${namePrefix}-scan'
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
      registries: [
        {
          server: registryServer
          identity: identity.id
        }
      ]
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
          args: args
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
}

output jobName string = job.name
