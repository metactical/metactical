<template>
  <div class="p-4 space-y-6">
    <div class="flex items-center justify-between">
      <h2 class="text-2xl font-bold">S3-SB-UploadManager</h2>
      
      <div class="flex items-center gap-3">
        <!-- Settings button -->
        <button 
          @click="showSettings = true"
          class="px-3 py-2 rounded-lg shadow transition-colors text-sm flex items-center gap-2"
          title="S3 Settings"
        >
          <svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"/>
            <path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/>
          </svg>
          Settings
        </button>
        
        <!-- Control buttons (only shown when images are selected) -->
        <div v-if="files.length" class="flex gap-3">
          <button 
            v-if="files.length"
            @click="exportData" 
            :disabled="!allFilesValid"
            class="px-4 py-2 rounded-lg shadow hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-400 transition-colors text-sm disabled:bg-gray-400 disabled:cursor-not-allowed"
          >
            Export JSON
          </button>
          <button 
            @click="startUpload" 
            :disabled="!canUpload || isUploading"
            class="bg-purple-500 px-4 py-2 rounded-lg shadow hover:bg-purple-600 focus:outline-none focus:ring-2 focus:ring-purple-400 transition-colors text-sm disabled:bg-gray-400 disabled:cursor-not-allowed flex items-center gap-2"
          >
            <svg v-if="isUploading" class="w-4 h-4 animate-spin" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/>
            </svg>
            <svg v-else class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"/>
            </svg>
            {{ isUploading ? 'Uploading...' : files.length > 0 ? 'Upload to S3' : 'Upload Metadata' }}
          </button>
          <button 
            v-if="files.length"
            @click="clearAllFiles" 
            class="bg-red-500 px-4 py-2 rounded-lg shadow hover:bg-red-600 focus:outline-none focus:ring-2 focus:ring-red-400 transition-colors text-sm"
          >
            Clear All
          </button>
        </div>
      </div>
    </div>

    <!-- Stats bar -->
    <div v-if="files.length" class="bg-gray-50 border rounded-lg p-4">
      <div class="flex items-center justify-between text-sm text-gray-600">
        <span>{{ files.length }} images uploaded</span>
        <span>{{ groupFilesByProduct().length }} products detected</span>
        <span>Roles: {{ [...new Set(files.map(f => f.role))].filter(r => r).join(', ') }}</span>
      </div>
    </div>

    <!-- Override Options -->
    <div v-if="files.length" class="border rounded-lg p-4 shadow-sm transition-colors"
         :class="overrideFullProduct ? 'bg-red-50 border-red-300' : 'bg-green-50 border-green-300'">
      <div class="flex items-center gap-4">
        <div class="flex items-center gap-3">
          <input
            type="checkbox"
            id="overrideFullProduct"
            v-model="overrideFullProduct"
            class="h-5 w-5 focus:ring-2 focus:ring-offset-2 border-2 rounded transition-colors"
            :class="overrideFullProduct ? 
              'text-red-600 focus:ring-red-500 border-red-400 bg-red-100' : 
              'text-green-600 focus:ring-green-500 border-green-400 bg-green-100'"
          />
          <label for="overrideFullProduct" class="text-sm font-bold cursor-pointer transition-colors"
                 :class="overrideFullProduct ? 'text-red-800' : 'text-green-800'">
            Override all images in existing full product
          </label>
        </div>
        
        <div class="flex-1 text-right">
          <span class="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium transition-colors"
                :class="overrideFullProduct ? 
                  'bg-red-200 text-red-800 border border-red-300' : 
                  'bg-green-200 text-green-800 border border-green-300'">
            {{ overrideFullProduct ? '⚠️ OVERRIDE MODE' : '✅ SAFE MODE' }}
          </span>
        </div>
      </div>
      
      <div class="mt-3 text-xs leading-relaxed transition-colors"
           :class="overrideFullProduct ? 'text-red-700' : 'text-green-700'">
        <div v-if="overrideFullProduct" class="font-medium">
          🔴 <strong>WARNING:</strong> When enabled, ALL existing images for this product will be completely replaced during upload.
          <br>This will remove any existing images not included in your current upload.
        </div>
        <div v-else class="font-medium">
          🟢 <strong>SAFE MODE:</strong> Only the specific images you're uploading will be added/updated.
          <br>Existing images for this product will be preserved.
        </div>
      </div>
    </div>

    <!-- Validation Status -->
    <div v-if="files.length > 0" class="border rounded-lg p-6 shadow-sm">
      <div class="space-y-3">
        <h3 class="text-lg font-semibold text-gray-800">Validation Status</h3>
        
        <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
          <!-- File Validation Status -->
          <div class="bg-gray-50 p-4 rounded-lg">
            <div class="flex items-center justify-between mb-2">
              <span class="text-sm font-medium text-gray-700">Files Complete</span>
              <span :class="validationSummary.valid === validationSummary.total ? 'text-green-600' : 'text-red-600'" 
                    class="text-sm font-bold">
                {{ validationSummary.valid }}/{{ validationSummary.total }}
              </span>
            </div>
            <div class="w-full bg-gray-200 rounded-full h-2">
              <div 
                class="h-2 rounded-full transition-all duration-300"
                :class="validationSummary.valid === validationSummary.total ? 'bg-green-500' : 'bg-red-500'"
                :style="{ width: `${(validationSummary.valid / validationSummary.total) * 100}%` }"
              ></div>
            </div>
          </div>

          <!-- S3 Configuration Status -->
          <div class="bg-gray-50 p-4 rounded-lg">
            <div class="flex items-center justify-between mb-2">
              <span class="text-sm font-medium text-gray-700">S3 Config</span>
              <span :class="isS3Configured ? 'text-green-600' : 'text-red-600'" 
                    class="text-sm font-bold">
                {{ isS3Configured ? '✓ Ready' : '✗ Missing' }}
              </span>
            </div>
            <div class="text-xs text-gray-500">
              {{ isS3Configured ? 'Credentials configured' : 'Click Settings to configure' }}
            </div>
          </div>

          <!-- Upload Ready Status -->
          <div class="bg-gray-50 p-4 rounded-lg">
            <div class="flex items-center justify-between mb-2">
              <span class="text-sm font-medium text-gray-700">Ready to Upload</span>
              <span :class="canUpload ? 'text-green-600' : 'text-red-600'" 
                    class="text-sm font-bold">
                {{ canUpload ? '✓ Yes' : '✗ No' }}
              </span>
            </div>
            <div class="text-xs text-gray-500">
              {{ canUpload ? 'All requirements met' : 'Complete validation & S3 config' }}
            </div>
          </div>
        </div>

        <!-- Missing Fields Summary -->
        <div v-if="!allFilesValid" class="mt-4 p-3 bg-yellow-50 border border-yellow-200 rounded-lg">
          <h4 class="text-sm font-medium text-yellow-800 mb-2">Missing Required Fields:</h4>
          <ul class="text-xs text-yellow-700 space-y-1">
            <li v-if="files.some(f => !f.role)">• Some images are missing role assignments</li>
            <li v-if="files.some(f => !f.skus || !f.skus.trim())">• Some images are missing SKU information</li>
            <li v-if="files.some(f => !f.sites || f.sites.length === 0)">• Some images have no sites selected</li>
            <li v-if="files.some(f => f.imageOrder === undefined || f.imageOrder === null)">• Some images are missing image order</li>
            <li v-if="files.some(f => f.isBroken && !f.file)">• Some images are broken and need replacement files</li>
          </ul>
        </div>

        <!-- Product Validation Messages -->
        <div v-if="getValidationSummary().incomplete > 0" class="mt-4 p-3 bg-red-50 border border-red-200 rounded-lg">
          <h4 class="text-sm font-medium text-red-800 mb-2">Validation Issues:</h4>
          <ul class="text-xs text-red-700 space-y-2">
            <li v-for="result in getValidationSummary().results.filter(r => !r.isComplete)" :key="result.productsku">
              <div class="font-medium">{{ result.productsku }}:</div>
              
              <!-- Export Issues -->
              <div v-if="result.exportIssues && result.exportIssues.length > 0" class="ml-2 mt-1">
                <div v-for="issue in result.exportIssues" :key="issue.type" class="text-red-800">
                  • <strong>Export Issue:</strong> {{ issue.message }}
                  <div v-if="issue.type === 'count_mismatch'" class="ml-4 text-xs">
                    UI has {{ issue.uiCount }} files, export has {{ issue.exportCount }} images
                  </div>
                  <div v-if="issue.fileName" class="ml-4 text-xs">
                    File: {{ issue.fileName }}
                    <span v-if="issue.expectedPath"> → Expected: {{ issue.expectedPath }}</span>
                    <span v-if="issue.imageOrder !== undefined"> (Order: {{ issue.imageOrder }})</span>
                  </div>
                </div>
              </div>
              
              <!-- Role Issues -->
              <div v-if="result.incompleteOrders && result.incompleteOrders.length > 0" class="ml-2 mt-1">
                <div v-for="incomplete in result.incompleteOrders" :key="incomplete.order">
                  • Missing {{ incomplete.missingRoles.join(', ') }} for order {{ incomplete.order }}
                </div>
              </div>
              
              <!-- Missing Roles -->
              <div v-if="result.missingRoles && result.missingRoles.length > 0" class="ml-2 mt-1">
                • Missing all roles: {{ result.missingRoles.join(', ') }}
              </div>
            </li>
          </ul>
        </div>
      </div>
    </div>

    <!-- Upload Progress -->
    <div v-if="isUploading || uploadComplete" class="border rounded-lg p-6 shadow-sm">
      <div class="space-y-4">
        <div class="flex items-center justify-between">
          <h3 class="text-lg font-semibold text-gray-800">Upload Progress</h3>
          <span class="text-sm text-gray-600">{{ uploadProgress.completed }} / {{ uploadProgress.total }}</span>
        </div>
        
        <!-- Overall Progress Bar -->
        <div class="w-full bg-gray-200 rounded-full h-3">
          <div 
            class="bg-blue-500 h-3 rounded-full transition-all duration-300 ease-in-out"
            :style="{ width: `${(uploadProgress.completed / uploadProgress.total) * 100}%` }"
          ></div>
        </div>
        
        <!-- Current File Upload -->
        <div v-if="currentUpload && !uploadComplete" class="bg-blue-50 rounded-lg p-4">
          <div class="flex items-center gap-3">
            <div class="w-2 h-2 bg-blue-500 rounded-full animate-pulse"></div>
            <div class="flex-1">
              <p class="text-sm font-medium text-blue-900">{{ currentUpload.status }}</p>
              <p class="text-xs text-blue-600">{{ currentUpload.filename }}</p>
            </div>
          </div>
        </div>
        
        <!-- Upload Complete -->
        <div v-if="uploadComplete" class="bg-green-50 rounded-lg p-4">
          <div class="flex items-center gap-3">
            <svg class="w-5 h-5 text-green-600" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7"/>
            </svg>
            <div class="flex-1">
              <p class="text-sm font-medium text-green-900">Upload Complete!</p>
              <p class="text-xs text-green-600">
                {{ uploadedFiles.length }} files uploaded successfully
                ({{ uploadedFiles.filter(f => !f.wasModified).length }} new, {{ uploadedFiles.filter(f => f.wasModified).length }} updated)
              </p>
            </div>
          </div>
        </div>
        
        <!-- Uploaded Files List -->
        <div v-if="uploadedFiles.length > 0" class="bg-blue-50 rounded-lg p-4">
          <div class="flex items-start gap-3">
            <svg class="w-5 h-5 text-blue-600 mt-0.5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>
            </svg>
            <div class="flex-1">
              <p class="text-sm font-medium text-blue-900">Uploaded Files ({{ uploadedFiles.length }})</p>
              <div class="mt-2 space-y-1 max-h-32 overflow-y-auto">
                <div v-for="file in uploadedFiles" :key="file.id" class="text-xs text-blue-700 font-mono">
                  <div class="flex flex-col">
                    <div class="flex items-center gap-2">
                      <span class="text-blue-800 font-medium">{{ file.s3Path }}</span>
                      <span v-if="file.wasModified" class="bg-yellow-100 text-yellow-800 text-xs px-1 py-0.5 rounded">
                        Updated
                      </span>
                      <span v-else class="bg-green-100 text-green-800 text-xs px-1 py-0.5 rounded">
                        New
                      </span>
                    </div>
                    <span class="text-blue-600 ml-2">({{ file.originalName }})</span>
                    <a v-if="file.fullUrl" :href="file.fullUrl" target="_blank" class="text-blue-500 hover:text-blue-700 underline text-xs">
                      Test URL: {{ file.fullUrl }}
                    </a>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
        
        <!-- Upload Errors -->
        <div v-if="uploadErrors.length > 0" class="bg-red-50 rounded-lg p-4">
          <div class="flex items-start gap-3">
            <svg class="w-5 h-5 text-red-600 mt-0.5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
            </svg>
            <div class="flex-1">
              <p class="text-sm font-medium text-red-900">Upload Errors ({{ uploadErrors.length }})</p>
              <div class="mt-2 space-y-1">
                <div v-for="error in uploadErrors" :key="error.id" class="text-xs text-red-600">
                  {{ error.filename }}: {{ error.message }}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Processing indicator (for when loading many files from folders) -->
    <div v-if="isProcessingFiles" class="bg-blue-50 border border-blue-200 rounded-lg p-4">
      <div class="flex items-center gap-3">
        <svg class="w-5 h-5 text-blue-600 animate-spin" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/>
        </svg>
        <div class="flex-1">
          <div class="flex items-center justify-between mb-1">
            <p class="text-sm font-medium text-blue-900">Processing Files from Folders</p>
            <span class="text-sm text-blue-600">{{ processingProgress.current }} / {{ processingProgress.total }}</span>
          </div>
          <div class="w-full bg-blue-200 rounded-full h-1.5 mb-2">
            <div 
              class="bg-blue-500 h-1.5 rounded-full transition-all duration-300"
              :style="{ width: `${(processingProgress.current / processingProgress.total) * 100}%` }"
            ></div>
          </div>
          <p class="text-xs text-blue-600">{{ processingProgress.filename }}</p>
        </div>
      </div>
    </div>

    <!-- Drop zone -->
    <div
      class="border-4 border-dashed rounded-md p-6 text-center transition-all duration-200 cursor-pointer"
      :class="{ 'border-blue-500 bg-blue-50': isDragOver, 'hover:shadow-lg': !isDragOver }"
      @dragover.prevent="onDragOver"
      @dragleave.prevent="onDragLeave"
      @drop.prevent="onDrop"
    >
      <div class="flex flex-col items-center gap-3">
        <svg class="w-12 h-12 text-gray-400" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"/>
        </svg>
        <div>
          <p class="text-gray-600 font-medium">Drag & drop images or folders here</p>
          <p class="text-sm text-gray-500">Supports individual files, folders, and nested subfolders</p>
        </div>
        <input type="file" multiple accept="image/*" @change="onSelect" class="hidden" ref="fileInput" />
        <button 
          class="bg-blue-500 px-4 py-2 rounded shadow hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-400 transition-colors"
          @click="$refs.fileInput.click()"
        >
          Browse Files
        </button>
      </div>
    </div>

    <!-- Image info list -->
    <div v-if="files.length" class="overflow-x-auto">
      <div class="flex flex-col gap-6 min-w-[340px] max-h-[70vh] overflow-y-auto pr-2">
        <div
          v-for="(file, idx) in files"
          :key="idx"
          class="border rounded-lg shadow-md hover:shadow-lg transition-shadow p-8 flex gap-8 min-w-[320px]"
        >
          <!-- Left side: Image only -->
          <div class="flex-shrink-0" style="width: 30vw;">
            <div class="w-full bg-gray-100 rounded overflow-hidden border border-gray-200" style="aspect-ratio: 1;">
              <img v-if="file.preview" :src="file.preview" alt="preview" class="w-full h-full object-contain" />
              <div v-else-if="file.isBroken" class="w-full h-full flex items-center justify-center bg-red-50 border-2 border-red-200">
                <div class="text-center p-4">
                  <svg class="w-16 h-16 text-red-400 mx-auto mb-2" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z"/>
                  </svg>
                  <p class="text-red-600 text-sm font-medium">Image Broken</p>
                  <p class="text-red-500 text-xs mt-1">File missing or corrupted</p>
                </div>
              </div>
              <div v-else class="w-full h-full flex items-center justify-center">
                <svg class="w-12 h-12 text-gray-400" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2z"/><path stroke-linecap="round" stroke-linejoin="round" d="M16 3v4M8 3v4"/></svg>
              </div>
            </div>
          </div>

          <!-- Right side: File info and Form inputs -->
          <div class="flex-1 space-y-12" style="margin-left: 3rem; padding-left: 2rem; margin-right: 2rem; padding-right: 1rem;">
            <!-- File info header -->
            <div class="border-b pb-8">
              <div class="flex items-center gap-2 mb-2">
                <div class="text-xl font-semibold text-gray-800 break-words max-w-md">{{ file.name }}</div>
                <!-- Broken Image Status Badge (highest priority) -->
                <div v-if="file.isBroken" class="bg-red-100 text-red-800 text-xs px-2 py-1 rounded-full border border-red-300">
                  🔴 Image Broken
                </div>
                <!-- Server Status Badges -->
                <div v-else-if="file.isOnServer" class="flex items-center gap-1">
                  <span v-if="isFileModified(file)" class="bg-yellow-100 text-yellow-800 text-xs px-2 py-1 rounded-full border border-yellow-300">
                    📝 Modified
                  </span>
                  <span v-else class="bg-green-100 text-green-800 text-xs px-2 py-1 rounded-full border border-green-300">
                    ☁️ On Server
                  </span>
                </div>
                <div v-else class="bg-blue-100 text-blue-800 text-xs px-2 py-1 rounded-full border border-blue-300">
                  🆕 New File
                </div>
              </div>
              <div class="text-sm text-gray-500 space-y-3">
                <div class="flex items-center">
                  <span class="font-medium w-20">Size:</span>
                  <span v-if="file.isBroken && (!file.width || !file.height)">Unknown (broken image)</span>
                  <span v-else>{{ file.width }}×{{ file.height }} px</span>
                </div>
                <div class="flex items-center">
                  <span class="font-medium w-20">Type:</span>
                  <span>{{ file.type }}</span>
                </div>
                <div class="flex items-center">
                  <span class="font-medium w-20">Product:</span>
                  <span class="text-blue-600 font-medium">{{ getBaseName(file.name) }}</span>
                </div>
                <div v-if="file.isOnServer" class="flex items-center">
                  <span class="font-medium w-20">S3 Path:</span>
                  <span class="text-gray-600 text-xs font-mono">{{ file.serverPath }}</span>
                </div>
                <div v-if="file.isBroken" class="flex items-center">
                  <span class="font-medium w-20">Status:</span>
                  <span class="text-red-600 font-medium">⚠️ Needs replacement before upload</span>
                </div>
              </div>
            </div>

            <!-- Update Image Button (only for server files) -->
            <div v-if="file.isOnServer" class="space-y-3">
              <label class="block text-sm font-medium text-gray-700">Update Image</label>
              <div class="flex items-center gap-3">
                <input 
                  type="file" 
                  accept="image/*" 
                  @change="updateServerFile(file, $event)" 
                  class="hidden" 
                  :ref="`fileInput-${idx}`" 
                />
                <button
                  @click="$refs[`fileInput-${idx}`][0].click()"
                  class="bg-orange-500 px-4 py-2 rounded-lg shadow hover:bg-orange-600 focus:outline-none focus:ring-2 focus:ring-orange-400 transition-colors text-sm flex items-center gap-2"
                >
                  <svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12"/>
                  </svg>
                  Replace Image
                </button>
                <span v-if="file.hasImageUpdate" class="text-xs bg-yellow-100 text-yellow-800 px-2 py-1 rounded-full">
                  📁 Image Updated
                </span>
              </div>
              <p class="text-xs text-gray-500">
                Replace the current server image with a new file
              </p>
            </div>

            <!-- Form inputs in stacked layout -->
            <div class="space-y-12 max-w-lg">
            <!-- Role selector -->
            <div class="space-y-3">
              <div class="flex items-center justify-between">
                <label class="block text-sm font-medium text-gray-700">Role</label>
                <span v-if="file.role" class="text-xs font-medium">🟢 Set</span>
                <span v-else class="text-xs font-medium">🔴 Missing</span>
              </div>
              <select v-model="file.role" @change="markAsModified(file)" class="w-64 border border-gray-300 rounded-lg px-4 py-3 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors">
                <option disabled value="">Select role...</option>
                <option value="icon">Icon (64×64px)</option>
                <option value="small">Small (175×175px)</option>
                <option value="medium">Medium (500×500px)</option>
                <option value="large">Large (500px+)</option>
              </select>
            </div>

            <!-- Image Order -->
            <div class="space-y-3">
              <label class="block text-sm font-medium text-gray-700">Image Order</label>
              <div class="flex items-center gap-3">
                <input
                  v-model.number="file.imageOrder"
                  @input="cascade('imageOrder', file); markAsModified(file)"
                  type="number"
                  class="w-32 border border-gray-300 rounded-lg px-4 py-3 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors text-center"
                  placeholder="0"
                  min="0"
                />
                <button
                  @click="setSequentialOrder(file)"
                  class="text-xs bg-gray-100 text-gray-600 px-3 py-2 rounded-md hover:bg-gray-200 transition-colors"
                  title="Increment order by 1 and copy to subsequent images"
                >
                  Next Image
                </button>
              </div>
              <p class="text-xs text-gray-500">
                Display order for multi-image products
                <span v-if="file.imageOrder >= 0" class="text-green-600">(Order: {{ file.imageOrder }})</span>
              </p>
            </div>

            <!-- SKUs (multi-text) -->
            <div class="space-y-3">
              <div class="flex items-center justify-between">
                <label class="block text-sm font-medium text-gray-700">SKUs</label>
                <span v-if="file.skus && file.skus.trim()" class="text-xs font-medium">🟢 Set</span>
                <span v-else class="text-xs font-medium">🔴 Missing</span>
              </div>
              <input
                v-model="file.skus"
                @input="cascadeForward('skus', file); markAsModified(file)"
                class="w-80 border border-gray-300 rounded-lg px-4 py-3 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
                placeholder="Comma-separated SKUs"
              />
            </div>

            <!-- Sites (multi-checkbox row) -->
            <div class="space-y-4">
              <div class="flex items-center justify-between">
                <label class="block text-sm font-medium text-gray-700 mb-3">Sites</label>
                <span v-if="file.sites.length > 0" class="text-xs font-medium">🟢 {{ file.sites.length }} selected</span>
                <span v-else class="text-xs font-medium">🔴 None selected</span>
              </div>
              <div class="flex flex-col gap-3 bg-gray-50 p-4 rounded-lg">
                <div v-for="site in siteList" :key="site" class="flex items-center">
                  <label class="inline-flex items-center cursor-pointer">
                    <input
                      type="checkbox"
                      v-model="file.sites"
                      :value="site"
                      @change="cascadeForward('sites', file); markAsModified(file)"
                      class="mr-3 accent-blue-500 focus:ring-2 focus:ring-blue-400 rounded"
                    />
                    <span class="text-sm text-gray-700">{{ site }}</span>
                  </label>
                </div>
              </div>
            </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Load from S3 Modal -->
    <div v-if="showLoadFromS3Modal" class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50" @click="showLoadFromS3Modal = false">
      <div class="rounded-lg shadow-xl p-6 w-full max-w-4xl max-h-[90vh] overflow-y-auto" @click.stop>
        <div class="flex items-center justify-between mb-6">
          <h3 class="text-xl font-semibold text-gray-800">Load from S3</h3>
          <button @click="showLoadFromS3Modal = false" class="text-gray-500 hover:text-gray-700">
            <svg class="w-6 h-6" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12"/>
            </svg>
          </button>
        </div>

        <!-- Search and Filter -->
        <div class="mb-6">
          <div class="flex gap-4 mb-4">
            <div class="flex-1">
              <input
                v-model="s3MetadataFilter"
                @input="filterS3Metadata"
                @keyup.enter="loadS3MetadataFiles"
                placeholder="Search by SKU prefix for server-side filtering, or any text for client-side... (Press Enter to refresh)"
                class="w-full border border-gray-300 rounded-lg px-4 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              />
              <p class="text-xs text-gray-500 mt-1">
                💡 Tip: SKU prefixes (e.g., "ABC" or "ABC-DEF") use fast server-side S3 filtering. Other searches filter locally.
                <span v-if="canUseServerSideFiltering" class="ml-2 text-green-600 font-medium">
                  ⚡ Server-side filtering active
                </span>
                <span v-else-if="s3MetadataFilter.trim()" class="ml-2 text-blue-600 font-medium">
                  🔍 Client-side filtering active
                </span>
              </p>
            </div>
            <button 
              @click="loadS3MetadataFiles"
              :disabled="isLoadingFromS3"
              class="bg-blue-500 px-4 py-2 rounded-lg shadow hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-400 transition-colors text-sm disabled:bg-gray-400 disabled:cursor-not-allowed"
            >
              {{ isLoadingFromS3 ? 'Loading...' : 'Refresh List' }}
            </button>
          </div>
          
          <!-- Filtering Information -->
          <div v-if="s3MetadataFilter.trim()" class="mb-4 p-3 bg-blue-50 border border-blue-200 rounded-lg">
            <div class="flex items-start gap-2">
              <svg class="w-4 h-4 text-blue-600 mt-0.5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
              </svg>
              <div class="text-sm text-blue-800">
                <span v-if="canUseServerSideFiltering">
                  <strong>Server-side filtering:</strong> S3 is searching for files starting with "{{ s3MetadataFilter.trim() }}" directly on the server. This is fast and efficient.
                </span>
                <span v-else>
                  <strong>Client-side filtering:</strong> Searching through loaded metadata files for "{{ s3MetadataFilter.trim() }}". 
                  <span class="text-blue-600">Use alphanumeric SKU prefixes for faster server-side filtering.</span>
                </span>
              </div>
            </div>
          </div>
          
          <!-- Metadata Files List -->
          <div v-if="s3MetadataFiles.length > 0" class="space-y-2 max-h-60 overflow-y-auto border border-gray-200 rounded-lg p-3">
            <div v-for="metaFile in filteredS3MetadataFiles" :key="metaFile.key" 
                 class="flex items-center justify-between p-3 bg-gray-50 rounded-lg hover:bg-gray-100 cursor-pointer"
                 @click="loadS3Metadata(metaFile)">
              <div class="flex-1">
                <div class="font-medium text-gray-800">{{ metaFile.filename }}</div>
                <div class="text-sm text-gray-600">
                  SKUs: {{ metaFile.skus.join(', ') }} | 
                  Last Modified: {{ new Date(metaFile.lastModified).toLocaleDateString() }}
                </div>
              </div>
              <button class="bg-green-500 px-3 py-1 rounded text-sm hover:bg-green-600">
                Load
              </button>
            </div>
          </div>
          
          <div v-else-if="!isLoadingFromS3" class="text-center py-8 text-gray-500">
            <div v-if="s3MetadataFilter.trim()">
              <p v-if="canUseServerSideFiltering">
                No metadata files found with SKU prefix "{{ s3MetadataFilter.trim() }}" on S3 server.
              </p>
              <p v-else>
                No metadata files match "{{ s3MetadataFilter.trim() }}" in loaded results.
              </p>
              <p class="text-xs mt-2">Try a different search term or clear the filter.</p>
            </div>
            <div v-else>
              No metadata files found. Click "Refresh List" to load from S3.
            </div>
          </div>
          
          <div v-if="isLoadingFromS3" class="text-center py-8">
            <div class="inline-flex items-center text-blue-600">
              <svg class="w-5 h-5 animate-spin mr-2" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/>
              </svg>
              Loading metadata files from S3...
            </div>
          </div>
        </div>

        <!-- Loading Progress -->
        <div v-if="s3LoadingProgress.total > 0" class="mb-6 bg-blue-50 rounded-lg p-4">
          <div class="flex items-center justify-between mb-2">
            <span class="text-sm font-medium text-blue-900">Loading Images from S3</span>
            <span class="text-sm text-blue-600">{{ s3LoadingProgress.completed }} / {{ s3LoadingProgress.total }}</span>
          </div>
          <div class="w-full bg-blue-200 rounded-full h-2">
            <div 
              class="bg-blue-500 h-2 rounded-full transition-all duration-300"
              :style="{ width: `${(s3LoadingProgress.completed / s3LoadingProgress.total) * 100}%` }"
            ></div>
          </div>
          <div v-if="s3LoadingProgress.current" class="text-xs text-blue-600 mt-1">
            {{ s3LoadingProgress.current }}
          </div>
        </div>

        <!-- Close Button -->
        <div class="flex justify-end">
          <button @click="showLoadFromS3Modal = false" class="bg-gray-500 px-4 py-2 rounded-lg hover:bg-gray-600">
            Close
          </button>
        </div>
      </div>
    </div>

    <!-- Settings Component -->
    <Settings
      :show="showSettings"
      :config="s3Config"
      @close="showSettings = false"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import Settings from './Settings.vue'

// Dotted path to the whitelisted backend endpoints for this page.
const API = 'metactical.metactical.page.s3_uploader.s3_uploader'

// Thin wrapper around frappe.call that returns the `message` payload.
const callBackend = (method, args = {}) =>
  new Promise((resolve, reject) => {
    frappe.call({
      method: `${API}.${method}`,
      args,
      callback: (r) => resolve(r.message),
      error: (r) => reject(r),
    })
  })

// Read a File as a base64 data string (no data: prefix).
const fileToBase64 = (file) =>
  new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => {
      const result = reader.result || ''
      const comma = result.indexOf(',')
      resolve(comma >= 0 ? result.slice(comma + 1) : result)
    }
    reader.onerror = reject
    reader.readAsDataURL(file)
  })

const fileInput = ref(null)
const files = ref([])
const showSettings = ref(false)
const overrideFullProduct = ref(false) // Default to true

// Upload state
const isUploading = ref(false)
const uploadComplete = ref(false)
const uploadProgress = ref({ completed: 0, total: 0 })
const currentUpload = ref(null)
const uploadErrors = ref([])
const uploadedFiles = ref([])

// S3 Load state
const showLoadFromS3Modal = ref(false)
const isLoadingFromS3 = ref(false)
const s3MetadataFiles = ref([])
const filteredS3MetadataFiles = ref([])
const s3MetadataFilter = ref('')
const s3LoadingProgress = ref({ completed: 0, total: 0, current: '' })

// File processing state
const isProcessingFiles = ref(false)
const processingProgress = ref({ current: 0, total: 0, filename: '' })
const isDragOver = ref(false)

// S3 Configuration (non-secret; comes from the S3 Settings doctype via the backend)
const s3Config = ref({
  disabled: true,
  bucket_name: '',
  region: '',
  base_prefix: 'images/products',
  public_url_base: ''
})

// Computed property to check if S3 is configured and enabled
const isS3Configured = computed(() => {
  return !s3Config.value.disabled && !!s3Config.value.bucket_name
})

// Computed property to check if all files are valid for upload/export
const allFilesValid = computed(() => {
  if (files.value.length === 0) return false
  
  return files.value.every(file => {
    return file.role && // Has role assigned
           file.skus && file.skus.trim() && // Has SKUs
           file.sites && file.sites.length > 0 && // Has sites selected
           (file.imageOrder >= 0) && // Has image order (including 0)
           (!file.isBroken || file.file) // Not broken OR has replacement file
  })
})

// Computed property to check if upload is possible
const canUpload = computed(() => {
  // Allow upload if S3 is configured and either:
  // 1. There are no files (metadata-only upload)
  // 2. All files are valid
  return isS3Configured.value && (files.value.length === 0 || allFilesValid.value)
})

// Computed property to get validation summary
const validationSummary = computed(() => {
  const total = files.value.length
  const valid = files.value.filter(file => 
    file.role && 
    file.skus && file.skus.trim() && 
    file.sites && file.sites.length > 0 && 
    (file.imageOrder >= 0) &&
    (!file.isBroken || file.file) // Include broken images as invalid unless they have a replacement file
  ).length
  
  return { total, valid, invalid: total - valid }
})

// Computed property to check if current filter can use server-side S3 filtering
const canUseServerSideFiltering = computed(() => {
  const filter = s3MetadataFilter.value.trim()
  return filter && /^[a-zA-Z0-9\-]+$/.test(filter)
})

const siteList = [
  'Website - RASUSA',
  'Website - CamoUSA',
  'Website - Gorilla',
  'Website - Zelen',
  'Website - MRK',
  'Website - Valley',
  'Website - RAS',
  'Website - GPD',
  'Website - Camo',
  'Website - FRN'
]

const onDrop = async (e) => {
  isDragOver.value = false
  const items = Array.from(e.dataTransfer.items)
  const allFiles = []
  
  // Process each dropped item (files or folders)
  for (const item of items) {
    if (item.kind === 'file') {
      const entry = item.webkitGetAsEntry()
      if (entry) {
        const files = await processEntry(entry)
        allFiles.push(...files)
      }
    }
  }
  
  // Filter for image files only
  const imageFiles = allFiles.filter(file => file.type.startsWith('image/'))
  
  if (imageFiles.length > 0) {
    await processFiles(imageFiles)
  } else {
    console.log('No image files found in dropped items')
  }
}

const onSelect = async (e) => {
  const selectedFiles = Array.from(e.target.files)
  await processFiles(selectedFiles)
}

// Recursive function to process directory entries
const processEntry = async (entry) => {
  const files = []
  
  if (entry.isFile) {
    // It's a file, add it to the list
    const file = await new Promise((resolve) => {
      entry.file(resolve)
    })
    files.push(file)
  } else if (entry.isDirectory) {
    // It's a directory, read its contents recursively
    const reader = entry.createReader()
    const entries = await new Promise((resolve) => {
      const allEntries = []
      
      const readEntries = () => {
        reader.readEntries((entries) => {
          if (entries.length === 0) {
            // No more entries, resolve with all collected entries
            resolve(allEntries)
          } else {
            // Add entries and continue reading
            allEntries.push(...entries)
            readEntries()
          }
        })
      }
      
      readEntries()
    })
    
    // Process each entry in the directory
    for (const childEntry of entries) {
      const childFiles = await processEntry(childEntry)
      files.push(...childFiles)
    }
  }
  
  return files
}

// Add drag state management
const onDragOver = (e) => {
  e.preventDefault()
  isDragOver.value = true
}

const onDragLeave = (e) => {
  e.preventDefault()
  isDragOver.value = false
}

const processFiles = async (incomingFiles) => {
  if (incomingFiles.length === 0) return
  
  isProcessingFiles.value = true
  processingProgress.value = { current: 0, total: incomingFiles.length, filename: '' }
  
  const newFiles = []
  
  try {
    for (let i = 0; i < incomingFiles.length; i++) {
      const file = incomingFiles[i]
      
      processingProgress.value.current = i + 1
      processingProgress.value.filename = file.name
      
      if (!file.type.startsWith('image/')) continue

      const img = await loadImage(file)
      // Prefer a role explicitly named in the filename, else detect it by size.
      const autoRole = detectRoleFromFilename(file.name) || determineRoleBySize(img.width, img.height)
      // Auto-fill the order from a numeric suffix in the filename (e.g. sku_2.jpg -> 2).
      const autoOrder = detectOrderFromFilename(file.name)

      newFiles.push({
        name: file.name,
        type: file.type,
        file,
        role: autoRole,
        width: img.width,
        height: img.height,
        skus: '',
        sites: [],
        imageOrder: autoOrder, // Auto-filled from filename, default 0
        preview: URL.createObjectURL(file),
        isOnServer: false, // Track if file exists on server
        serverPath: null, // S3 path if file exists on server
        isModified: false // Track if file has been modified since loading from server
      })
      
      // Small delay to allow UI updates for large batches
      if (i % 10 === 0) {
        await new Promise(resolve => setTimeout(resolve, 10))
      }
    }
    
    // Add to files array and auto-sort
    files.value.push(...newFiles)
    autoSortFiles()
    
    console.log(`Successfully processed ${newFiles.length} image files from ${incomingFiles.length} total files`)
    
  } finally {
    isProcessingFiles.value = false
    processingProgress.value = { current: 0, total: 0, filename: '' }
  }
}

const loadImage = (file) => {
  return new Promise((resolve) => {
    const img = new Image()
    img.onload = () => resolve(img)
    img.src = URL.createObjectURL(file)
  })
}

const determineRoleBySize = (width, height) => {
  // Define exact size matches for each role
  const sizeRules = [
    // Icon sizes - exact 64x64
    { role: 'icon', width: 64, height: 64, tolerance: 5 },
    // Small images - exact 175x175
    { role: 'small', width: 175, height: 175, tolerance: 5 },
    // Medium images - exact 500x500
    { role: 'medium', width: 500, height: 500, tolerance: 5 }
  ]

  // Check for exact matches with small tolerance
  for (const rule of sizeRules) {
    const widthMatch = Math.abs(width - rule.width) <= rule.tolerance
    const heightMatch = Math.abs(height - rule.height) <= rule.tolerance
    
    if (widthMatch && heightMatch) {
      return rule.role
    }
  }

  // Check for larger images (anything bigger than medium)
  if (width > 505 || height > 505) { // 500 + tolerance
    return 'large'
  }

  // Fallback logic based on closest size
  const distances = [
    { role: 'icon', distance: Math.abs(width - 64) + Math.abs(height - 64) },
    { role: 'small', distance: Math.abs(width - 175) + Math.abs(height - 175) },
    { role: 'medium', distance: Math.abs(width - 500) + Math.abs(height - 500) }
  ]

  // Return the role with the smallest distance
  const closest = distances.reduce((min, current) => 
    current.distance < min.distance ? current : min
  )

  return closest.role
}

const getBaseName = (filename) => {
  return filename.replace(/\.(jpe?g|png)$/i, '').replace(/_(icon|small|medium|large)$/i, '')
}

// Detect an explicit role suffix in the filename, e.g. "vm01_icon.jpg" -> "icon".
const detectRoleFromFilename = (filename) => {
  const match = filename.replace(/\.(jpe?g|png)$/i, '').match(/_(icon|small|medium|large)$/i)
  return match ? match[1].toLowerCase() : null
}

// Detect a numeric order suffix in the filename, e.g. "vm01_2.jpg" -> 2 (default 0).
const detectOrderFromFilename = (filename) => {
  const base = filename.replace(/\.(jpe?g|png)$/i, '').replace(/_(icon|small|medium|large)$/i, '')
  const match = base.match(/_(\d+)$/)
  return match ? parseInt(match[1], 10) : 0
}

// Helper function to normalize filename extensions to lowercase
// Examples: "image.JPG" -> "image.jpg", "photo.PNG" -> "photo.png"
const normalizeFilename = (filename) => {
  const parts = filename.split('.')
  if (parts.length < 2) return filename
  
  const extension = parts.pop().toLowerCase()
  return [...parts, extension].join('.')
}

const cascade = (field, changedFile) => {
  const base = getBaseName(changedFile.name)
  for (const f of files.value) {
    if (getBaseName(f.name) === base) {
      f[field] = JSON.parse(JSON.stringify(changedFile[field])) // deep clone
    }
  }
}

const cascadeForward = (field, changedFile) => {
  const index = files.value.findIndex(f => f.name === changedFile.name)
  const value = JSON.parse(JSON.stringify(changedFile[field]))
  for (let i = index + 1; i < files.value.length; i++) {
    files.value[i][field] = value
  }
}

// Generate S3 filename for a file
const generateS3Filename = (file) => {
  const skuList = file.skus ? file.skus.split(',').map(s => s.trim()).filter(s => s) : []
  const order = file.imageOrder || 0
  const extension = file.name.split('.').pop().toLowerCase() // Convert extension to lowercase
  
  if (skuList.length > 0) {
    // Use only the first SKU for filename
    // Special case: if order is 0, use just SKU.extension
    if (order === 0) {
      return `${skuList[0]}.${extension}`
    } else {
      return `${skuList[0]}_${order}.${extension}`
    }
  } else {
    // Fallback to base name if no SKUs
    const baseName = getBaseName(file.name)
    if (order === 0) {
      return `${baseName}.${extension}`
    } else {
      return `${baseName}_${order}.${extension}`
    }
  }
}

// Auto-sort files based on image order and product grouping
const autoSortFiles = () => {
  files.value.sort((a, b) => {
    const baseA = getBaseName(a.name)
    const baseB = getBaseName(b.name)
    
    // First sort by product name (base name)
    if (baseA !== baseB) {
      return baseA.localeCompare(baseB)
    }
    
    // Then sort by image order within the same product
    return (a.imageOrder || 999) - (b.imageOrder || 999)
  })
}

// Create S3 metadata structure with products array containing productsku, sites, and ordered images
const createS3Metadata = () => {
  const productsByFirstSku = {}
  
  // Group files by their first SKU and organize by order and role
  files.value.forEach(file => {
    const skuList = file.skus ? file.skus.split(',').map(s => s.trim()).filter(s => s) : []
    
    if (skuList.length > 0) {
      const firstSku = skuList[0]
      
      if (!productsByFirstSku[firstSku]) {
        productsByFirstSku[firstSku] = {
          productsku: skuList, // Store all SKUs as an array
          sites: [...file.sites],
          overrideFullProduct: overrideFullProduct.value, // Add override flag
          images: []
        }
      } else {
        // Merge additional SKUs that aren't already included
        skuList.forEach(sku => {
          if (!productsByFirstSku[firstSku].productsku.includes(sku)) {
            productsByFirstSku[firstSku].productsku.push(sku)
          }
        })
        
        // Merge sites
        file.sites.forEach(site => {
          if (!productsByFirstSku[firstSku].sites.includes(site)) {
            productsByFirstSku[firstSku].sites.push(site)
          }
        })
      }
    }
  })
  
  // Now organize images by order for each product
  files.value.forEach(file => {
    const skuList = file.skus ? file.skus.split(',').map(s => s.trim()).filter(s => s) : []
    
    if (skuList.length > 0 && file.role) {
      const firstSku = skuList[0]
      const order = file.imageOrder !== undefined ? file.imageOrder : 0
      
      if (productsByFirstSku[firstSku]) {
        // Find existing image set for this order, or create new one
        let imageSet = productsByFirstSku[firstSku].images.find(img => img.order === order)
        if (!imageSet) {
          imageSet = {
            order: order,
            icon: null,
            small: null,
            medium: null,
            large: null
          }
          productsByFirstSku[firstSku].images.push(imageSet)
        }
        
        // Set the image path for this role (using first SKU only in filename)
        const existingImage = imageSet[file.role]
        if (existingImage) {
          console.warn(`Duplicate ${file.role} image for ${firstSku} at order ${order}:`, {
            existing: existingImage,
            new: `products/${file.role}/${generateS3Filename(file)}`,
            file: file.name
          })
        }
        
        imageSet[file.role] = `products/${file.role}/${generateS3Filename(file)}`
      }
    }
  })
  
  // Sort images by order for each product
  Object.values(productsByFirstSku).forEach(product => {
    product.images.sort((a, b) => a.order - b.order)
  })
  
  return {
    products: Object.values(productsByFirstSku)
  }
}

// Validate product completeness and export accuracy
const validateProductCompleteness = () => {
  const metadata = createS3Metadata()
  const validationResults = []
  
  // First, validate that all files are accounted for in the export
  const exportValidation = validateExportCompleteness(metadata)
  
  metadata.products.forEach(product => {
    const validation = {
      productsku: Array.isArray(product.productsku) ? product.productsku.join(', ') : product.productsku,
      isComplete: true,
      missingRoles: [],
      incompleteOrders: [],
      hasAllSizes: true,
      exportIssues: [] // New field for export-specific issues
    }
    
    // Check if this product has export issues
    const productExportIssues = exportValidation.productIssues.filter(issue => 
      issue.productSku === (Array.isArray(product.productsku) ? product.productsku[0] : product.productsku)
    )
    
    if (productExportIssues.length > 0) {
      validation.exportIssues = productExportIssues
      validation.isComplete = false
    }
    
    if (product.images.length === 0) {
      validation.isComplete = false
      validation.hasAllSizes = false
      validation.missingRoles = ['icon', 'small', 'medium', 'large']
      validation.exportIssues.push({
        type: 'no_images',
        message: 'No images found in export for this product'
      })
      validationResults.push(validation)
      return
    }
    
    // Check each order for all 4 roles (icon, small, medium, large)
    const requiredRoles = ['icon', 'small', 'medium', 'large']
    product.images.forEach(imageSet => {
      const missingRoles = requiredRoles.filter(role => !imageSet[role])
      
      if (missingRoles.length > 0) {
        validation.incompleteOrders.push({
          order: imageSet.order,
          missingRoles: missingRoles
        })
        validation.isComplete = false
        validation.hasAllSizes = false
      }
    })
    
    validationResults.push(validation)
  })
  
  // Add overall export validation to results
  if (exportValidation.hasIssues) {
    validationResults.unshift({
      productsku: '⚠️ EXPORT VALIDATION',
      isComplete: false,
      missingRoles: [],
      incompleteOrders: [],
      hasAllSizes: false,
      exportIssues: exportValidation.globalIssues
    })
  }
  
  return validationResults
}

// New function to validate that export includes all files
const validateExportCompleteness = (metadata) => {
  const issues = {
    hasIssues: false,
    globalIssues: [],
    productIssues: []
  }
  
  // Count total files in UI vs export
  const totalFilesInUI = files.value.length
  const totalImagesInExport = metadata.products.reduce((total, product) => {
    return total + product.images.reduce((imageCount, imageSet) => {
      return imageCount + ['icon', 'small', 'medium', 'large'].filter(role => imageSet[role]).length
    }, 0)
  }, 0)
  
  if (totalFilesInUI !== totalImagesInExport) {
    issues.hasIssues = true
    issues.globalIssues.push({
      type: 'count_mismatch',
      message: `File count mismatch: ${totalFilesInUI} files in UI but only ${totalImagesInExport} in export`,
      uiCount: totalFilesInUI,
      exportCount: totalImagesInExport
    })
  }
  
  // Check each file to see if it appears in export
  files.value.forEach(file => {
    const skuList = file.skus ? file.skus.split(',').map(s => s.trim()).filter(s => s) : []
    
    if (skuList.length === 0) {
      issues.hasIssues = true
      issues.productIssues.push({
        type: 'missing_sku',
        productSku: 'UNKNOWN',
        fileName: file.name,
        message: `File "${file.name}" has no SKUs and cannot be exported`
      })
      return
    }
    
    if (!file.role) {
      issues.hasIssues = true
      issues.productIssues.push({
        type: 'missing_role',
        productSku: skuList[0],
        fileName: file.name,
        message: `File "${file.name}" has no role assigned`
      })
      return
    }
    
    // Check if this file appears in the export
    const firstSku = skuList[0]
    const product = metadata.products.find(p => 
      Array.isArray(p.productsku) ? p.productsku.includes(firstSku) : p.productsku === firstSku
    )
    
    if (!product) {
      issues.hasIssues = true
      issues.productIssues.push({
        type: 'product_not_found',
        productSku: firstSku,
        fileName: file.name,
        message: `File "${file.name}" with SKU "${firstSku}" not found in export`
      })
      return
    }
    
    // Check if the specific image appears in any image set
    const expectedFilename = generateS3Filename(file)
    const expectedPath = `products/${file.role}/${expectedFilename}`
    
    const imageFound = product.images.some(imageSet => imageSet[file.role] === expectedPath)
    
    if (!imageFound) {
      issues.hasIssues = true
      issues.productIssues.push({
        type: 'image_not_found',
        productSku: firstSku,
        fileName: file.name,
        expectedPath: expectedPath,
        imageOrder: file.imageOrder,
        message: `File "${file.name}" (order: ${file.imageOrder}) not found in export for product ${firstSku}`
      })
    }
  })
  
  // Check for duplicate orders within products
  metadata.products.forEach(product => {
    const orderCounts = {}
    product.images.forEach(imageSet => {
      const order = imageSet.order
      if (!orderCounts[order]) {
        orderCounts[order] = 0
      }
      orderCounts[order]++
    })
    
    Object.entries(orderCounts).forEach(([order, count]) => {
      if (count > 1) {
        issues.hasIssues = true
        issues.productIssues.push({
          type: 'duplicate_order',
          productSku: Array.isArray(product.productsku) ? product.productsku[0] : product.productsku,
          message: `Product has ${count} image sets with order ${order} - orders must be unique`,
          duplicateOrder: parseInt(order)
        })
      }
    })
  })
  
  return issues
}

// Get validation summary for display
const getValidationSummary = () => {
  const validationResults = validateProductCompleteness()
  const total = validationResults.length
  const complete = validationResults.filter(v => v.isComplete).length
  const incomplete = total - complete
  
  return {
    total,
    complete,
    incomplete,
    results: validationResults
  }
}

// Export functionality for parsed image data
const exportData = () => {
  // Create the metadata structure that will be uploaded to S3
  const metadataForS3 = createS3Metadata()
  
  // For local export, include only essential debugging info
  const exportData = {
    s3_metadata: metadataForS3,
    debug_info: {
      timestamp: new Date().toISOString(),
      totalImages: files.value.length,
      totalProducts: metadataForS3.products.length,
      exportVersion: "2.0", // Updated version for new structure
      appName: "S3-SB-UploadManager"
    }
  }
  
  // Create download link
  const blob = new Blob([JSON.stringify(exportData, null, 2)], { 
    type: 'application/json' 
  })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `s3-upload-data-${new Date().toISOString().split('T')[0]}.json`
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}

// Group files by product (base name) for export
const groupFilesByProduct = () => {
  const groups = {}
  
  files.value.forEach(file => {
    const baseName = getBaseName(file.name)
    if (!groups[baseName]) {
      groups[baseName] = {
        productName: baseName,
        imageCount: 0,
        roles: [],
        skus: [],
        sites: []
      }
    }
    
    groups[baseName].imageCount++
    if (!groups[baseName].roles.includes(file.role)) {
      groups[baseName].roles.push(file.role)
    }
    
    // Collect unique SKUs
    if (file.skus) {
      const fileSKUs = file.skus.split(',').map(s => s.trim()).filter(s => s)
      fileSKUs.forEach(sku => {
        if (!groups[baseName].skus.includes(sku)) {
          groups[baseName].skus.push(sku)
        }
      })
    }
    
    // Collect unique sites
    file.sites.forEach(site => {
      if (!groups[baseName].sites.includes(site)) {
        groups[baseName].sites.push(site)
      }
    })
  })
  
  return Object.values(groups)
}

// Clear all files
const clearAllFiles = () => {
  files.value.forEach(file => {
    if (file.preview) {
      URL.revokeObjectURL(file.preview)
    }
  })
  files.value = []
  
  // Clear upload history
  uploadComplete.value = false
  uploadProgress.value = { completed: 0, total: 0 }
  currentUpload.value = null
  uploadErrors.value = []
  uploadedFiles.value = []
}

// Get role distribution for export
const getRoleDistribution = () => {
  const distribution = {}
  files.value.forEach(file => {
    const role = file.role || 'unassigned'
    distribution[role] = (distribution[role] || 0) + 1
  })
  return distribution
}

// Get site distribution for export
const getSiteDistribution = () => {
  const distribution = {}
  files.value.forEach(file => {
    file.sites.forEach(site => {
      distribution[site] = (distribution[site] || 0) + 1
    })
  })
  return distribution
}

// Set sequential order starting from current file
const setSequentialOrder = (currentFile) => {
  // Increment the current file's order by 1
  currentFile.imageOrder = (currentFile.imageOrder || 0) + 1
  
  // Find the index of the current file
  const currentIndex = files.value.findIndex(f => f.name === currentFile.name)
  
  // Set the same order number for all subsequent files
  for (let i = currentIndex + 1; i < files.value.length; i++) {
    files.value[i].imageOrder = currentFile.imageOrder
  }
  
  // Also cascade the current file's order to same-product images
  cascade('imageOrder', currentFile)
}

// S3 Configuration Management — non-secret config comes from the S3 Settings doctype.
const loadS3Config = async () => {
  try {
    const config = await callBackend('get_public_config')
    if (config) {
      s3Config.value = config
    }
  } catch (error) {
    console.error('Error loading S3 config:', error)
  }
}

// Function to update a server file with a new image
const updateServerFile = async (file, event) => {
  const newFile = event.target.files[0]
  if (!newFile || !newFile.type.startsWith('image/')) {
    return
  }

  try {
    // Load the new image to get dimensions
    const img = await loadImage(newFile)
    
    // Update the file object with new image data
    file.file = newFile
    file.width = img.width
    file.height = img.height
    file.type = newFile.type
    
    // Update preview
    if (file.preview) {
      URL.revokeObjectURL(file.preview)
    }
    file.preview = URL.createObjectURL(newFile)
    
    // Mark as having an image update and as modified
    file.hasImageUpdate = true
    file.isModified = true
    
    // If this was a broken image, mark it as no longer broken
    if (file.isBroken) {
      file.isBroken = false
      file.needsReupload = false
    }
    
    console.log(`Updated image for ${file.name} with new file: ${newFile.name}`)
  } catch (error) {
    console.error('Failed to update server file:', error)
  }
  
  // Clear the input value so the same file can be selected again
  event.target.value = ''
}

// Modified upload functionality
const startUpload = async () => {
  if (!canUpload.value) {
    return
  }
  
  // Reset upload state
  isUploading.value = true
  uploadComplete.value = false
  
  // Upload all files (no smart filtering - always re-upload everything)
  const imagesToUpload = files.value
  
  // Always upload metadata regardless of whether there are files or not
  const metadataChanged = true
  
  uploadProgress.value = { 
    completed: 0, 
    total: imagesToUpload.length + 1 // Always include metadata
  }
  uploadErrors.value = []
  uploadedFiles.value = []
  currentUpload.value = null
  
  try {
    // Upload images one at a time so the progress bar reflects each file.
    // The backend uploads via boto3 and HEAD-verifies each object.
    for (let i = 0; i < imagesToUpload.length; i++) {
      const file = imagesToUpload[i]

      // Skip broken images that don't have a file to upload
      if (file.isBroken && !file.file) {
        uploadErrors.value.push({
          id: Date.now() + i,
          filename: file.name,
          message: 'Image is broken and needs to be replaced before uploading'
        })
        uploadProgress.value.completed = i + 1
        continue
      }

      currentUpload.value = {
        filename: file.name,
        status: `Uploading image ${i + 1} of ${imagesToUpload.length} (${file.isOnServer ? 'Re-uploading' : 'New'})`
      }

      try {
        const s3Filename = generateS3Filename(file)
        const content = await fileToBase64(file.file)

        const result = await callBackend('upload_image', {
          filename: s3Filename,
          role: file.role,
          content,
          content_type: file.type
        })

        // Track uploaded file (verified = backend HEAD check passed)
        uploadedFiles.value.push({
          id: Date.now() + i,
          originalName: file.name,
          s3Path: result.key,
          s3Filename: s3Filename,
          fullUrl: result.full_url,
          verified: result.verified,
          wasModified: file.isOnServer // Mark as modified if it was already on server
        })

        // Update file status - always mark as on server after upload
        if (!file.isOnServer) {
          file.isOnServer = true
          file.serverPath = result.key
        }

        // Reset flags since we've uploaded
        file.hasImageUpdate = false
        file.isModified = false
        file.isBroken = false // No longer broken after successful upload
        file.needsReupload = false // No longer needs reupload
        file.originalServerData = {
          role: file.role,
          skus: file.skus.split(',').map(s => s.trim()).filter(s => s),
          sites: [...file.sites],
          imageOrder: file.imageOrder,
          filename: s3Filename
        }

      } catch (error) {
        console.error(`Failed to upload ${file.name}:`, error)
        uploadErrors.value.push({
          id: Date.now() + i,
          filename: file.name,
          message: (error && error.message) || 'Upload failed'
        })
      }

      uploadProgress.value.completed = i + 1
    }

    // Save metadata to the S3 Product Image Meta Data doctype (not to S3)
    if (metadataChanged) {
      currentUpload.value = {
        filename: 'metadata',
        status: 'Saving metadata...'
      }

      try {
        const metadata = createS3Metadata()

        const result = await callBackend('save_metadata', {
          products: JSON.stringify(metadata.products)
        })

        const recordCount = (result && result.records) ? result.records.length : metadata.products.length
        uploadedFiles.value.push({
          id: Date.now() + 10000,
          originalName: 'Product metadata',
          s3Path: 'S3 Product Image Meta Data',
          s3Filename: `${recordCount} record(s)`,
          verified: true,
          wasModified: false // Metadata is always new/updated
        })

        // Reset all modification flags since metadata is now synced
        files.value.forEach(file => {
          if (file.isOnServer) {
            file.isModified = false
          }
        })

      } catch (error) {
        console.error('Failed to save metadata:', error)
        uploadErrors.value.push({
          id: Date.now(),
          filename: 'metadata',
          message: (error && error.message) || 'Metadata save failed'
        })
      }

      uploadProgress.value.completed = uploadProgress.value.total
    }
    
    uploadComplete.value = true
    
    if (uploadErrors.value.length === 0) {
      console.log('Upload completed successfully!')
      console.log(`Images uploaded: ${imagesToUpload.length}, Metadata updated: ${metadataChanged}`)
    } else {
      console.log(`Upload completed with ${uploadErrors.value.length} errors`)
    }
    
  } catch (error) {
    console.error('Upload failed:', error)
    uploadErrors.value.push({
      id: Date.now(),
      filename: 'Upload process',
      message: error.message || 'Unknown error occurred'
    })
  } finally {
    isUploading.value = false
    currentUpload.value = null
  }
}

// S3 Load functionality
const loadS3MetadataFiles = async () => {
  if (!isS3Configured.value) {
    console.error('S3 not configured')
    return
  }

  isLoadingFromS3.value = true
  s3MetadataFiles.value = []
  
  try {
    const filter = s3MetadataFilter.value.trim()

    // Backend returns submitted S3 Product Image Meta Data records.
    const records = await callBackend('list_metadata', { filter: filter || null })

    s3MetadataFiles.value = (records || []).map(record => ({
      key: record.name,                  // doctype record name (used by loadS3Metadata)
      filename: record.product_sku,      // shown in the list
      skus: record.skus || [record.product_sku],
      lastModified: record.modified,
      size: null
    }))

    // Apply client-side filtering to the loaded results
    filterS3Metadata()

  } catch (error) {
    console.error('Failed to load metadata records:', error)
  } finally {
    isLoadingFromS3.value = false
  }
}

const filterS3Metadata = () => {
  const filter = s3MetadataFilter.value.toLowerCase().trim()
  if (!filter) {
    filteredS3MetadataFiles.value = s3MetadataFiles.value
    return
  }
  
  // Always apply client-side filtering to whatever results we have
  // (whether they came from server-side filtering or not)
  filteredS3MetadataFiles.value = s3MetadataFiles.value.filter(file => 
    file.filename.toLowerCase().includes(filter) ||
    file.skus.some(sku => sku.toLowerCase().includes(filter))
  )
}

const loadS3Metadata = async (metaFile) => {
  if (!isS3Configured.value) return

  isLoadingFromS3.value = true
  s3LoadingProgress.value = { completed: 0, total: 0, current: 'Loading metadata...' }
  
  try {
    // Fetch the single S3 Product Image Meta Data record, shaped as one product.
    const product = await callBackend('get_metadata', { name: metaFile.key })
    const metadata = { products: [product] }

    // Clear existing files
    clearAllFiles()

    // Process metadata and load images - handle both old and new structures
    const allImages = []
    
    // Check if it's the new array-based structure or old object-based structure
    if (Array.isArray(metadata.products)) {
      // New array-based structure
      metadata.products.forEach(product => {
        product.images.forEach(imageSet => {
          // Extract images from each role in the image set
          const roles = ['icon', 'small', 'medium', 'large']
          roles.forEach(role => {
            if (imageSet[role]) {
              // Parse the image path to get filename
              const imagePath = imageSet[role]
              const filename = normalizeFilename(imagePath.split('/').pop()) // Normalize extension to lowercase
              
              // Filter sites to only include valid ones from siteList (remove legacy domains)
              const validSites = product.sites.filter(site => siteList.includes(site))
              
              // Handle both array and string productsku formats
              const skus = Array.isArray(product.productsku) ? product.productsku : [product.productsku]
              
              allImages.push({
                productName: skus[0], // Use first SKU as product name
                role,
                imageInfo: {
                  filename,
                  order: imageSet.order
                },
                skus: skus,
                sites: validSites
              })
            }
          })
        })
      })
    } else {
      // Old object-based structure (for backward compatibility)
      Object.entries(metadata.products).forEach(([productName, productData]) => {
        Object.entries(productData.images).forEach(([role, images]) => {
          images.forEach(imageInfo => {
            // Filter sites to only include valid ones from siteList (remove legacy domains)
            const validSites = productData.sites.filter(site => siteList.includes(site))
            
            allImages.push({
              productName,
              role,
              imageInfo,
              skus: productData.skus,
              sites: validSites
            })
          })
        })
      })
    }

    s3LoadingProgress.value.total = allImages.length
    s3LoadingProgress.value.completed = 0

    // Load each image
    for (let i = 0; i < allImages.length; i++) {
      const { productName, role, imageInfo, skus, sites } = allImages[i]
      
      s3LoadingProgress.value.current = `Loading ${imageInfo.filename}...`
      
      let fileObj = null
      let isImageBroken = false
      
      try {
        const normalizedImageFilename = normalizeFilename(imageInfo.filename)
        const imageUrl = `${s3Config.value.public_url_base}/${s3Config.value.base_prefix}/${role}/${normalizedImageFilename}`
        
        // Check if image exists
        const headResponse = await fetch(imageUrl, { method: 'HEAD' })
        if (!headResponse.ok) {
          console.warn(`Image not found: ${imageUrl}`)
          isImageBroken = true
        } else {
          // Fetch the image
          const imageResponse = await fetch(imageUrl)
          if (!imageResponse.ok) {
            console.warn(`Failed to fetch image: ${imageUrl}`)
            isImageBroken = true
          } else {
            const imageBlob = await imageResponse.blob()
            const normalizedFilename = normalizeFilename(imageInfo.originalName || imageInfo.filename)
            const imageFile = new File([imageBlob], normalizedFilename, {
              type: imageBlob.type || 'image/jpeg'
            })

            // Load image to get dimensions
            try {
              const img = await loadImage(imageFile)
              
              // Create file object with working image
              fileObj = {
                name: normalizedFilename,
                type: imageFile.type,
                file: imageFile,
                role: role,
                width: imageInfo.dimensions?.width || img.width,
                height: imageInfo.dimensions?.height || img.height,
                skus: skus.join(', '),
                sites: [...sites],
                imageOrder: imageInfo.order || 0,
                preview: URL.createObjectURL(imageFile),
                isOnServer: true,
                serverPath: `images/products/${role}/${normalizeFilename(imageInfo.filename)}`, // Use normalized filename for server path too
                isModified: false,
                isBroken: false,
                originalServerData: {
                  role,
                  skus: [...skus],
                  sites: [...sites],
                  imageOrder: imageInfo.order || 0,
                  filename: normalizeFilename(imageInfo.filename) // Store normalized filename
                }
              }
            } catch (imgError) {
              console.error(`Failed to load image dimensions for ${imageInfo.filename}:`, imgError)
              isImageBroken = true
            }
          }
        }
      } catch (error) {
        console.error(`Failed to load image ${imageInfo.filename}:`, error)
        isImageBroken = true
      }
      
      // If image is broken, create a placeholder file object with metadata
      if (isImageBroken) {
        const normalizedFilename = normalizeFilename(imageInfo.originalName || imageInfo.filename)
        fileObj = {
          name: normalizedFilename,
          type: 'image/jpeg', // Default type for broken images
          file: null, // No actual file
          role: role,
          width: imageInfo.dimensions?.width || 0,
          height: imageInfo.dimensions?.height || 0,
          skus: skus.join(', '),
          sites: [...sites],
          imageOrder: imageInfo.order || 0,
          preview: null, // No preview for broken images
          isOnServer: true,
          serverPath: `images/products/${role}/${normalizeFilename(imageInfo.filename)}`, // Use normalized filename
          isModified: false,
          isBroken: true, // Mark as broken
          needsReupload: true, // Needs to be re-uploaded
          originalServerData: {
            role,
            skus: [...skus],
            sites: [...sites],
            imageOrder: imageInfo.order || 0,
            filename: normalizeFilename(imageInfo.filename) // Store normalized filename
          }
        }
      }
      
      if (fileObj) {
        files.value.push(fileObj)
      }
      
      s3LoadingProgress.value.completed = i + 1
    }

    // Auto-sort loaded files
    autoSortFiles()
    
    // Close modal
    showLoadFromS3Modal.value = false
    s3LoadingProgress.value = { completed: 0, total: 0, current: '' }
    
    console.log(`Loaded ${files.value.length} images from S3`)
    
  } catch (error) {
    console.error('Failed to load metadata:', error)
  } finally {
    isLoadingFromS3.value = false
  }
}

// Function to mark a file as modified
const markAsModified = (file) => {
  if (file.isOnServer) {
    file.isModified = true
  }
}

// Function to check if a file has been modified since loading from server
const isFileModified = (file) => {
  if (!file.isOnServer || !file.originalServerData) return false
  
  const original = file.originalServerData
  return (
    file.role !== original.role ||
    file.skus !== original.skus.join(', ') ||
    JSON.stringify(file.sites.sort()) !== JSON.stringify(original.sites.sort()) ||
    file.imageOrder !== original.imageOrder
  )
}

// Load S3 config on mount
onMounted(() => {
  loadS3Config()
})

// Reload config (used by the page's "refresh" toolbar action)
const refresh = () => {
  loadS3Config()
}

defineExpose({ refresh })
</script>
