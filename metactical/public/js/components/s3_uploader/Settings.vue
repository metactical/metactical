<template>
  <div>
    <div v-if="show" class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4" style="z-index: 9999;" @click="$emit('close')">
      <div class="bg-gray-50 rounded-2xl shadow-2xl max-w-lg w-full max-h-[90vh] overflow-y-auto transform transition-all duration-300 scale-100" @click.stop>
        <!-- Header -->
        <div class="flex items-center justify-between p-6 border-b border-gray-200 bg-gray-50 from-blue-50 to-indigo-50 rounded-t-2xl">
          <div class="flex items-center gap-3">
            <div class="w-10 h-10 bg-gray-50 from-blue-500 to-blue-600 rounded-xl flex items-center justify-center shadow-lg">
              <svg class="w-5 h-5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"/>
                <path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/>
              </svg>
            </div>
            <div>
              <h3 class="text-xl font-bold text-gray-800">S3 Configuration</h3>
              <p class="text-sm text-gray-600">Credentials are managed in the S3 Settings doctype</p>
            </div>
          </div>
          <button @click="$emit('close')" class="btn btn-default btn-sm" title="Close">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12"/>
            </svg>
          </button>
        </div>

        <!-- Content -->
        <div class="p-6 space-y-6">
          <!-- Server Info Display (read-only, from S3 Settings) -->
          <div class="bg-blue-50 rounded-lg p-4 border border-blue-200">
            <div class="flex items-start gap-3">
              <div class="flex-shrink-0">
                <svg class="w-5 h-5 text-blue-600" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
                </svg>
              </div>
              <div>
                <h4 class="text-sm font-medium text-blue-900">Server Configuration</h4>
                <p class="text-sm text-blue-700 mt-1">
                  <span class="font-medium">Bucket:</span> {{ config.bucket_name || '—' }}
                </p>
                <p class="text-sm text-blue-700 mt-1">
                  <span class="font-medium">Region:</span> {{ config.region || '—' }}
                </p>
                <p class="text-sm text-blue-700 mt-1">
                  <span class="font-medium">Endpoint:</span> {{ config.public_url_base || '—' }}
                </p>
                <p class="text-xs text-blue-600 mt-2">
                  Edit credentials in
                  <a href="/app/s3-settings" target="_blank" class="underline font-medium">S3 Settings</a>.
                </p>
              </div>
            </div>
          </div>

          <!-- Configuration Status -->
          <div class="bg-gray-50 rounded-lg p-4 border border-gray-200">
            <div class="flex items-center gap-3">
              <div v-if="connectionStatus === 'valid'" class="flex items-center gap-2 text-green-700">
                <div class="w-2 h-2 bg-green-500 rounded-full animate-pulse"></div>
                <span class="text-sm font-medium">🚀 Connection verified</span>
              </div>
              <div v-else-if="connectionStatus === 'invalid'" class="flex items-center gap-2 text-red-700">
                <div class="w-2 h-2 bg-red-500 rounded-full animate-pulse"></div>
                <span class="text-sm font-medium">❌ Connection failed</span>
              </div>
              <div v-else-if="connectionStatus === 'testing'" class="flex items-center gap-2 text-blue-700">
                <div class="w-2 h-2 bg-blue-500 rounded-full animate-pulse"></div>
                <span class="text-sm font-medium">🔄 Testing connection...</span>
              </div>
              <div v-else-if="config.disabled" class="flex items-center gap-2 text-amber-600">
                <div class="w-2 h-2 bg-amber-500 rounded-full animate-pulse"></div>
                <span class="text-sm font-medium">⚠️ Uploader disabled</span>
              </div>
              <div v-else-if="isConfigured" class="flex items-center gap-2 text-amber-600">
                <div class="w-2 h-2 bg-amber-500 rounded-full animate-pulse"></div>
                <span class="text-sm font-medium">⚠️ Click test to verify</span>
              </div>
              <div v-else class="flex items-center gap-2 text-amber-600">
                <div class="w-2 h-2 bg-amber-500 rounded-full animate-pulse"></div>
                <span class="text-sm font-medium">⚠️ Not configured</span>
              </div>
            </div>
            <p class="text-xs text-gray-600 mt-2">
              {{ getStatusMessage() }}
            </p>
            <!-- Error message display -->
            <div v-if="connectionError" class="mt-3 p-3 bg-red-50 border border-red-200 rounded-lg">
              <p class="text-xs text-red-700 font-medium">Connection Error:</p>
              <p class="text-xs text-red-600 mt-1">{{ connectionError }}</p>
            </div>
            <!-- Success message display -->
            <div v-if="connectionStatus === 'valid'" class="mt-3 p-3 bg-green-50 border border-green-200 rounded-lg">
              <p class="text-xs text-green-700 font-medium">✅ Connection Successful!</p>
              <p class="text-xs text-green-600 mt-1">S3 credentials verified by the server.</p>
            </div>
          </div>
        </div>

        <!-- Footer -->
        <div class="flex items-center justify-between p-6 border-t border-gray-200 bg-gray-50 rounded-b-2xl">
          <div class="text-sm text-gray-600">
            <span v-if="connectionStatus === 'valid'" class="flex items-center gap-2">
              <span class="text-green-600">🟢</span>
              <span class="font-medium">Connection verified</span>
            </span>
            <span v-else-if="connectionStatus === 'invalid'" class="flex items-center gap-2">
              <span class="text-red-600">🔴</span>
              <span class="font-medium">Connection failed</span>
            </span>
            <span v-else-if="isConfigured" class="flex items-center gap-2">
              <span class="text-amber-600">🟡</span>
              <span class="font-medium">Ready to test</span>
            </span>
            <span v-else class="flex items-center gap-2">
              <span class="text-gray-400">⚪</span>
              <span class="font-medium">Not configured</span>
            </span>
          </div>
          <div class="flex items-center gap-3">
            <button
              @click="$emit('close')"
              class="btn btn-default btn-sm"
            >
              Close
            </button>
            <button
              @click="testConnection"
              :disabled="!canTest || isValidating"
              class="btn btn-primary btn-sm flex items-center gap-2"
            >
              <span class="flex items-center gap-2">
                <svg v-if="isValidating" class="w-4 h-4 animate-spin" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/>
                </svg>
                <svg v-else class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7"/>
                </svg>
                {{ isValidating ? 'Testing Connection...' : 'Test Connection' }}
              </span>
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'

const API = 'metactical.metactical.page.s3_uploader.s3_uploader'

const props = defineProps({
  show: Boolean,
  config: {
    type: Object,
    default: () => ({
      disabled: true,
      bucket_name: '',
      region: '',
      public_url_base: ''
    })
  }
})

defineEmits(['close'])

// Connection validation state
const isValidating = ref(false)
const connectionStatus = ref('') // '', 'testing', 'valid', 'invalid'
const connectionError = ref('')

// Reset connection status whenever the config changes
watch(() => props.config, () => {
  connectionStatus.value = ''
  connectionError.value = ''
}, { deep: true })

// Configuration is usable when enabled and a bucket is set
const isConfigured = computed(() => {
  return !props.config.disabled && !!props.config.bucket_name
})

// A connection test is read-only, so allow it whenever a bucket is set —
// even while the uploader is disabled (uploads still require enabling).
const canTest = computed(() => !!props.config.bucket_name)

// Get status message based on current state
const getStatusMessage = () => {
  switch (connectionStatus.value) {
    case 'valid':
      return 'S3 connection verified successfully. Ready to upload files.'
    case 'invalid':
      return 'Failed to connect to S3. Check the credentials in S3 Settings.'
    case 'testing':
      return 'Testing connection to S3 server...'
    default:
      if (props.config.disabled) {
        return 'The uploader is disabled. Uncheck "Disabled" in S3 Settings to enable it.'
      }
      return isConfigured.value
        ? 'Click "Test Connection" to verify access to S3.'
        : 'Set the bucket, region and credentials in S3 Settings to enable uploads.'
  }
}

// Test the S3 connection via the backend (boto3)
const testConnection = () => {
  if (!canTest.value) {
    connectionStatus.value = 'invalid'
    connectionError.value = 'Set a bucket in S3 Settings before testing.'
    return
  }

  isValidating.value = true
  connectionStatus.value = 'testing'
  connectionError.value = ''

  frappe.call({
    method: `${API}.test_connection`,
    callback: (r) => {
      const result = r.message || {}
      if (result.success) {
        connectionStatus.value = 'valid'
      } else {
        connectionStatus.value = 'invalid'
        connectionError.value = result.message || 'Connection failed.'
      }
      isValidating.value = false
    },
    error: () => {
      connectionStatus.value = 'invalid'
      connectionError.value = 'Connection test failed. See the browser console / server logs.'
      isValidating.value = false
    }
  })
}
</script>
