<template>
  <div class="p-4 space-y-6">
    <div class="flex items-center justify-between">
      <h2 class="text-2xl font-bold">S3 SB Upload Manager</h2>
      
      <div class="flex items-center gap-3">
        <!-- Control buttons (only shown when images are selected) -->
        <div v-if="files.length" class="flex gap-3">
          <button
            @click="startUpload"
            :disabled="!canUpload || isUploading"
            class="btn btn-primary btn-sm flex items-center gap-2"
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
            class="btn btn-danger btn-sm"
          >
            Clear All
          </button>
        </div>
      </div>
    </div>

    <!-- Product template (locks the whole upload to one template's variants) -->
    <div class="border rounded-lg p-4 shadow-sm"
         :class="templateItem ? 'bg-green-50 border-green-300' : 'border-yellow-300'">
      <div class="flex items-center gap-4">
        <div class="flex-1">
          <label class="block text-sm font-bold mb-1"
                 :class="templateItem ? 'text-green-800' : ''">
            Product Template
          </label>
          <div ref="templateRef"></div>
          <p class="text-xs mt-1" :class="templateItem ? 'text-green-700' : ''">
            <template v-if="isLoadingFromS3">
              Loading existing record…
            </template>
            <template v-else-if="templateItem">
              {{ templateVariants.length }} variant{{ templateVariants.length === 1 ? '' : 's' }} —
              every variant must have all 4 size images.
            </template>
            <template v-else>
              Select a product template first. Each image can then only use this template's variants.
            </template>
          </p>
        </div>
        <span v-if="templateItem"
              class="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium bg-green-200 text-green-800 border border-green-300">
          🔒 {{ templateItem }}
        </span>
      </div>
    </div>

    <!-- Image Orders (set how many image sets each variant should have) -->
    <div v-if="templateItem" class="border rounded-lg p-4 shadow-sm">
      <label class="block text-sm font-bold mb-2">Image Orders</label>
      <div class="flex items-center gap-3">
        <input
          v-model.number="orderCount"
          type="number"
          min="1"
          class="w-24 border border-gray-300 rounded-lg px-3 py-2 text-sm text-center"
          @keyup.enter="applyOrderCount"
        />
        <button @click="applyOrderCount" class="btn btn-default btn-sm">Add Orders</button>
        <span class="text-xs text-gray-500">
          = 4 sizes × {{ Math.max(orderCount || 1, 1) }} orders
          = <strong>{{ 4 * Math.max(orderCount || 1, 1) }}</strong> upload slots
          ({{ templateVariants.length }} variant{{ templateVariants.length === 1 ? '' : 's' }} share each image)
        </span>
      </div>
      <p class="text-xs text-gray-500 mt-2">
        Sets this many image sets. Increasing adds empty icon/small/medium/large slots;
        decreasing removes the extra orders. All variants share each image.
      </p>
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
        
        <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
          <!-- File Validation Status -->
          <div class="bg-gray-50 p-4 rounded-lg">
            <div class="flex items-center justify-between mb-2">
              <span class="text-sm font-medium text-gray-700">Files Complete</span>
              <span :class="validationSummary.valid >= expectedImageCount ? 'text-green-600' : 'text-red-600'"
                    class="text-sm font-bold">
                {{ validationSummary.valid }}/{{ expectedImageCount }}
              </span>
            </div>
            <div class="w-full bg-gray-200 rounded-full h-2">
              <div
                class="h-2 rounded-full transition-all duration-300"
                :class="validationSummary.valid >= expectedImageCount ? 'bg-green-500' : 'bg-red-500'"
                :style="{ width: `${Math.min(100, (validationSummary.valid / Math.max(expectedImageCount, 1)) * 100)}%` }"
              ></div>
            </div>
          </div>

          <!-- Variant Completeness Status -->
          <div class="bg-gray-50 p-4 rounded-lg">
            <div class="flex items-center justify-between mb-2">
              <span class="text-sm font-medium text-gray-700">Variants Complete</span>
              <span :class="productValid ? 'text-green-600' : 'text-red-600'"
                    class="text-sm font-bold">
                {{ templateItem ? `${templateVariants.length - variantImageIssues.length}/${templateVariants.length}` : '—' }}
              </span>
            </div>
            <div class="text-xs text-gray-500">
              {{ templateItem ? 'Every variant needs all 4 size images' : 'Select a template' }}
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
        <div v-if="!allFilesValid" class="mt-4 p-3 border border-yellow-200 rounded-lg">
          <h4 class="text-sm font-medium text-yellow-800 mb-2">Missing Required Fields:</h4>
          <ul class="text-xs space-y-1">
            <li v-if="files.some(f => !f.file && !f.isOnServer)">• Some slots still need an image uploaded</li>
            <li v-if="files.some(f => !f.role)">• Some images are missing role assignments</li>
            <li v-if="files.some(f => !f.skus || !f.skus.trim())">• Some images are missing SKU information</li>
            <li v-if="files.some(f => !f.sites || f.sites.length === 0)">• Some images have no sites selected</li>
            <li v-if="files.some(f => f.imageOrder === undefined || f.imageOrder === null)">• Some images are missing image order</li>
            <li v-if="files.some(f => f.isBroken && !f.file)">• Some images are broken and need replacement files</li>
          </ul>
        </div>

        <!-- Template / Variant Completeness Messages -->
        <div v-if="!templateItem" class="mt-4 p-3 border border-yellow-200 rounded-lg">
          <p class="text-sm text-yellow-800">• Select a product template — uploads must be tied to one template.</p>
        </div>
        <div v-else-if="variantImageIssues.length > 0" class="mt-4 p-3 bg-red-50 border border-red-200 rounded-lg">
          <h4 class="text-sm font-medium text-red-800 mb-2">Variant image issues:</h4>
          <ul class="text-xs text-red-700 space-y-1">
            <li v-for="v in variantImageIssues" :key="v.sku">
              <template v-if="v.kind === 'unassigned'">
                • <strong>{{ v.sku }}</strong> ({{ v.item_code }}) has not been assigned images —
                upload at least 1 image (4 sizes) or assign it to existing images.
              </template>
              <template v-else>
                • <strong>{{ v.sku }}</strong> ({{ v.item_code }}) missing {{ v.missing.join(', ') }}
              </template>
            </li>
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

    <!-- Drop zone (disabled when S3 is off / not configured) -->
    <div
      class="border-4 border-dashed rounded-md p-6 text-center transition-all duration-200"
      :class="!isS3Configured
        ? 'opacity-50 cursor-not-allowed'
        : (isDragOver ? 'border-blue-500 bg-blue-50 cursor-pointer' : 'hover:shadow-lg cursor-pointer')"
      @dragover.prevent="isS3Configured ? onDragOver($event) : null"
      @dragleave.prevent="onDragLeave"
      @drop.prevent="isS3Configured ? onDrop($event) : null"
    >
      <div class="flex flex-col items-center gap-3">
        <svg class="w-12 h-12 text-gray-400" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"/>
        </svg>
        <div>
          <p class="text-gray-600 font-medium">Drag & drop images or folders here</p>
          <p class="text-sm text-gray-500">Supports individual files, folders, and nested subfolders</p>
          <p v-if="!isS3Configured" class="text-sm text-red-600 font-medium mt-1">
            S3 is currently disabled. Please contact the administrator.
          </p>
        </div>
        <input type="file" multiple accept="image/*" @change="onSelect" class="hidden" ref="fileInput" :disabled="!isS3Configured" />
        <button
          :disabled="!isS3Configured"
          class="bg-blue-500 px-4 py-2 rounded shadow hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-400 transition-colors disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:bg-blue-500"
          @click="isS3Configured && $refs.fileInput.click()"
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

            <!-- Add Image (scaffolded slot awaiting an upload) -->
            <div v-else-if="!file.file" class="space-y-3">
              <label class="block text-sm font-medium text-gray-700">Image</label>
              <div class="flex items-center gap-3">
                <input
                  type="file"
                  accept="image/*"
                  @change="addImageToPlaceholder(file, $event)"
                  class="hidden"
                  :ref="`addImg-${idx}`"
                />
                <button
                  @click="$refs[`addImg-${idx}`][0].click()"
                  class="btn btn-primary btn-sm flex items-center gap-2"
                >
                  <svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12"/>
                  </svg>
                  Add Image
                </button>
                <span class="text-xs bg-yellow-100 text-yellow-800 px-2 py-1 rounded-full">Needs image</span>
              </div>
              <p class="text-xs text-gray-500">
                Upload the <strong>{{ file.role }}</strong> image for <strong>{{ file.skus }}</strong>
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

            <!-- SKUs (native grid: Add Row to enter, select + Delete to remove) -->
            <div class="space-y-3">
              <div class="flex items-center justify-between">
                <label class="block text-sm font-medium text-gray-700">SKUs</label>
                <span v-if="file.skuItems && file.skuItems.length" class="text-xs font-medium">🟢 {{ file.skuItems.length }} set</span>
                <span v-else class="text-xs font-medium">🔴 Missing</span>
              </div>
              <SkuManager
                :sku-items="file.skuItems"
                :template="templateItem"
                :allowed-variants="templateVariants"
                @update="(items) => updateSkuItems(file, items)"
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
                <div v-if="siteList.length === 0" class="text-xs text-gray-500">
                  No sites available. Add a Lead Source with a Lead Source Domain.
                </div>
                <div v-for="site in siteList" :key="site.name" class="flex items-center">
                  <label class="inline-flex items-center cursor-pointer">
                    <input
                      type="checkbox"
                      v-model="file.sites"
                      :value="site.name"
                      @change="cascadeForward('sites', file); markAsModified(file)"
                      class="mr-3 accent-blue-500 focus:ring-2 focus:ring-blue-400 rounded"
                    />
                    <span class="text-sm text-gray-700">
                      {{ site.name }}
                      <span v-if="site.lead_source_domain" class="text-gray-500"> ({{ site.lead_source_domain }})</span>
                    </span>
                  </label>
                </div>
              </div>
            </div>
            </div>
          </div>
        </div>
      </div>
    </div>

  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import SkuManager from './SkuManager.vue'

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

// Convert a base64 string (from the backend) into a Blob.
const base64ToBlob = (b64, type) => {
  const chars = atob(b64)
  const bytes = new Uint8Array(chars.length)
  for (let i = 0; i < chars.length; i++) bytes[i] = chars.charCodeAt(i)
  return new Blob([bytes], { type: type || 'application/octet-stream' })
}

const fileInput = ref(null)
const files = ref([])
const overrideFullProduct = ref(false) // Default to true

// One product template per upload. All per-image SKU pickers are limited to this
// template's variants, and every variant must have all 4 images before upload/export.
const templateItem = ref(null)            // resolved template Item name
const templateVariants = ref([])          // [{ item_code, sku }] — the allowed variants
const templateRef = ref(null)             // DOM node for the native Link control
let templateControl = null
const ROLES = ['icon', 'small', 'medium', 'large']

// One empty placeholder card for a (role, order) holding ALL the template's variants —
// awaiting an image upload. The image is shared by every variant in its SKU grid.
const buildRoleCard = (role, order) => {
  const firstSku = (templateVariants.value[0] && templateVariants.value[0].sku) || ''
  return {
    name: order ? `${firstSku}_${order}_${role}.jpg` : `${firstSku}_${role}.jpg`,
    type: null,
    file: null,
    role,
    width: 0,
    height: 0,
    skus: templateVariants.value.map(v => v.sku).join(', '),
    skuItems: templateVariants.value.map(v => ({ item_code: v.item_code, sku: v.sku })),
    newItemCode: '',
    skuError: '',
    resolvingItem: false,
    sites: [],
    imageOrder: order,
    preview: null,
    isOnServer: false,
    serverPath: null,
    isModified: false,
    isPlaceholder: true,
  }
}

// Scaffold one image order: just the 4 size cards (icon/small/medium/large), each
// carrying every variant — so any number of variants still produces only 4 uploads.
const scaffoldOrder = (order) => {
  files.value.push(...ROLES.map(role => buildRoleCard(role, order)))
}

// Build the default order 0 slots (4 sizes; all variants share each image).
const scaffoldVariantCards = () => scaffoldOrder(0)

// `orderCount` = the live number in the input (drives only the info hint).
// `appliedOrderCount` = the orders actually committed (set on "Add Orders" / scaffold / load);
// this is what the Files Complete denominator uses, so typing alone doesn't change it.
const orderCount = ref(1)
const appliedOrderCount = ref(1)

// Which orders currently have cards.
const existingOrders = computed(() => new Set(files.value.map(f => f.imageOrder)))

// Add an order's empty 4-size slots for every variant (no-op if it already exists).
const addOrderSlots = (order) => {
  if (existingOrders.value.has(order)) return
  scaffoldOrder(order)
}

// Remove every card of an order (revoking previews) — drops it from the working set.
const removeOrder = (order) => {
  files.value.forEach(f => {
    if (f.imageOrder === order && f.preview) URL.revokeObjectURL(f.preview)
  })
  files.value = files.value.filter(f => f.imageOrder !== order)
}

// Set the product to exactly `n` orders: keep/create orders 0..n-1 (4 size slots each),
// and remove any order >= n. e.g. 5 orders × 4 sizes = 20 upload slots (any # of variants).
const applyOrderCount = () => {
  const n = Math.max(1, Math.floor(orderCount.value || 1))
  orderCount.value = n
  appliedOrderCount.value = n
  ;[...existingOrders.value].filter(o => o >= n).forEach(o => removeOrder(o))
  for (let o = 0; o < n; o++) addOrderSlots(o)
}

// Expected number of images = 4 sizes × orders (variants share each image, so the count
// is independent of how many variants there are). Uses the *applied* order count so the
// denominator only changes on "Add Orders"; never drops below the orders already present.
const expectedImageCount = computed(() => {
  if (!templateItem.value) return files.value.length
  const orders = Math.max(appliedOrderCount.value || 1, existingOrders.value.size, 1)
  return ROLES.length * orders
})

// Clear the file cards (and upload history) without touching the chosen template.
const resetFiles = () => {
  files.value.forEach(file => {
    if (file.preview) URL.revokeObjectURL(file.preview)
  })
  files.value = []
  uploadComplete.value = false
  uploadProgress.value = { completed: 0, total: 0 }
  currentUpload.value = null
  uploadErrors.value = []
  uploadedFiles.value = []
}

// Load every image stored on a saved record (by name) into the editor.
const loadRecordImages = async (recordName) => {
  const metadata = await callBackend('get_metadata', { name: recordName })
  // Restore the override flag so the checkbox reflects the saved record.
  overrideFullProduct.value = !!metadata.overrideFullProduct
  const allImages = (metadata.images || []).map(im => {
    const filename = normalizeFilename(im.path.split('/').pop())
    const skuItems = im.skuItems || []
    return {
      productName: (skuItems[0] && skuItems[0].sku) || '',
      role: im.role,
      imageInfo: { filename, order: im.order || 0 },
      skus: skuItems.map(i => i.sku),
      skuItems,
      sites: (im.sites || []).filter(site => siteNames.value.includes(site))
    }
  })
  // Fix the order count up-front (from the data) so the x/total denominator doesn't
  // change while images stream in below.
  orderCount.value = appliedOrderCount.value = Math.max(new Set(allImages.map(i => i.imageInfo?.order || 0)).size, 1)
  await loadAllImages(allImages)
}

// Resolve the picked Item to its template + variant set, then either load the
// template's existing record (if one exists) or scaffold fresh upload slots.
const applyTemplateFromItem = async (itemCode) => {
  if (!itemCode) {
    templateItem.value = null
    templateVariants.value = []
    resetFiles()
    return
  }

  // S3 must be enabled to start a product. Keep the picker usable but block selection.
  if (!isS3Configured.value) {
    frappe.msgprint({
      title: __('S3 is disabled'),
      message: __('S3 is currently disabled. Please contact the administrator.'),
      indicator: 'red',
    })
    templateItem.value = null
    templateVariants.value = []
    resetFiles()
    if (templateControl) templateControl.set_value('')
    return
  }

  try {
    const res = await callBackend('get_item_family', { item_code: itemCode })
    templateItem.value = (res && (res.template || itemCode)) || null
    templateVariants.value = (res && res.items) || []
  } catch (e) {
    console.error('Failed to resolve template:', e)
    frappe.show_alert({ message: `Failed to resolve ${itemCode}`, indicator: 'red' })
    return
  }

  // Start clean for the newly chosen template.
  resetFiles()

  // If a record already exists for this template, load it; otherwise scaffold slots.
  let existing = null
  try {
    existing = await callBackend('find_template_record', { template_item: templateItem.value })
  } catch (e) {
    console.error('Failed to look up template record:', e)
  }

  if (existing && existing.name) {
    isLoadingFromS3.value = true
    s3LoadingProgress.value = { completed: 0, total: 0, current: 'Loading record…' }
    try {
      await loadRecordImages(existing.name)
      frappe.show_alert({ message: `Loaded existing record: ${existing.name}`, indicator: 'green' })
    } catch (e) {
      console.error('Failed to load existing record:', e)
      frappe.show_alert({ message: 'Failed to load the existing record', indicator: 'red' })
    } finally {
      isLoadingFromS3.value = false
      s3LoadingProgress.value = { completed: 0, total: 0, current: '' }
    }
  } else if (templateVariants.value.length) {
    // No new-system record yet — check the OLD S3 system before scaffolding.
    let legacy = null
    try {
      legacy = await callBackend('find_legacy_meta', { skus: JSON.stringify(templateVariants.value.map(v => v.sku)) })
    } catch (e) {
      console.error('Failed to check the old system:', e)
    }
    const matches = (legacy && legacy.matches) || []
    if (matches.length === 0) {
      scaffoldAndNotify()
    } else if (matches.length === 1) {
      promptMigrateOrCreate(matches[0].key)
    } else {
      promptChooseLegacy(matches)
    }
  }

  // Reflect the resolved template back into the picker input.
  if (templateControl && templateItem.value && templateControl.get_value() !== templateItem.value) {
    templateControl.set_value(templateItem.value)
  }
}

// Build the 4 size slots (all variants share each) and announce it.
const scaffoldAndNotify = () => {
  resetFiles()
  scaffoldVariantCards()
  orderCount.value = 1
  appliedOrderCount.value = 1
  frappe.show_alert({ message: `Created ${ROLES.length} upload slots (4 sizes) for ${templateVariants.value.length} variant${templateVariants.value.length === 1 ? '' : 's'}`, indicator: 'blue' })
}

// Small popup when old-system data exists: migrate it, or start fresh.
const promptMigrateOrCreate = (metaKey) => {
  const d = new frappe.ui.Dialog({
    title: __('Found in old system'),
    primary_action_label: __('Migrate'),
    primary_action: () => { d.hide(); migrateFromLegacy(metaKey) },
  })
  d.$body.html(
    `<div style="padding:6px 0 12px">This product already has data in the old S3 system. ` +
    `Do you want to <b>migrate</b> that data, or <b>create a new</b> upload?</div>`
  )
  d.set_secondary_action_label(__('Create new'))
  d.set_secondary_action(() => { d.hide(); scaffoldAndNotify() })
  d.show()
}

// Several old-system files match this template — let the user pick which one to import.
const promptChooseLegacy = (matches) => {
  const byLabel = {}
  matches.forEach(m => {
    const label = `${m.name}  (${(m.skus || []).join(', ')})`
    byLabel[label] = m.key
  })
  const labels = Object.keys(byLabel)
  const d = new frappe.ui.Dialog({
    title: __('Multiple matches found'),
    fields: [
      {
        fieldtype: 'Select',
        fieldname: 'meta',
        label: __('Old-system file'),
        options: labels.join('\n'),
        default: labels[0],
        reqd: 1,
      },
    ],
    primary_action_label: __('Import selected'),
    primary_action: (values) => {
      const key = byLabel[values.meta]
      d.hide()
      if (key) migrateFromLegacy(key)
    },
  })
  d.$wrapper.find('.modal-body').prepend(
    `<div style="padding:6px 16px 0;font-size:12px;color:var(--text-muted)">` +
    `Multiple files in the old system match this template. Pick one to import — going forward, ` +
    `only the data you save into ERP will be used.</div>`
  )
  d.set_secondary_action_label(__('Create new'))
  d.set_secondary_action(() => { d.hide(); scaffoldAndNotify() })
  d.show()
}

// Migrate a product from the old system: load its legacy metadata JSON + images.
const migrateFromLegacy = async (metaKey) => {
  isLoadingFromS3.value = true
  s3LoadingProgress.value = { completed: 0, total: 0, current: 'Migrating from old system…' }
  try {
    const res = await callBackend('get_s3_meta', { key: metaKey })
    if (!res || !res.found) {
      frappe.show_alert({ message: 'Old metadata not found; creating new', indicator: 'orange' })
      scaffoldAndNotify()
      return
    }
    const metadata = res.metadata || {}
    resetFiles()

    const LEGACY_ROLES = ['icon', 'small', 'medium', 'large']
    // Dedupe by (role, order, filename); combine SKUs + sites of each referencing product.
    const byKey = {}
    const addImage = (role, order, filename, skus, sites) => {
      if (!filename) return
      const fn = normalizeFilename(filename)
      const key = `${role}|${order}|${fn}`
      if (!byKey[key]) byKey[key] = { role, order, filename: fn, skus: new Set(), sites: new Set() }
      skus.forEach(s => s && byKey[key].skus.add(s))
      sites.forEach(s => s && byKey[key].sites.add(s))
    }

    if (Array.isArray(metadata.products)) {
      metadata.products.forEach(product => {
        const skus = Array.isArray(product.productsku) ? product.productsku : [product.productsku].filter(Boolean)
        const sites = product.sites || []
        ;(product.images || []).forEach(imageSet => {
          LEGACY_ROLES.forEach(role => {
            if (imageSet[role]) addImage(role, imageSet.order || 0, String(imageSet[role]).split('/').pop(), skus, sites)
          })
        })
      })
    } else if (metadata.products && typeof metadata.products === 'object') {
      Object.values(metadata.products).forEach(productData => {
        const skus = productData.skus || []
        const sites = productData.sites || []
        Object.entries(productData.images || {}).forEach(([role, imgs]) => {
          ;(imgs || []).forEach(info => addImage(role, info.order || 0, info.filename, skus, sites))
        })
      })
    }

    // Resolve SKUs → item codes (legacy JSON only carries SKUs).
    const allSkus = [...new Set(Object.values(byKey).flatMap(v => [...v.skus]))]
    let itemBySku = {}
    if (allSkus.length) {
      try {
        itemBySku = (await callBackend('resolve_item_codes', { skus: JSON.stringify(allSkus) })) || {}
      } catch (e) {
        console.error('Failed to resolve item codes:', e)
      }
    }

    // Keep only images that belong to this template's variants.
    const allowedSku = new Set(templateVariants.value.map(v => v.sku))
    const allImages = Object.values(byKey).map(v => {
      const skus = [...v.skus].filter(s => allowedSku.has(s))
      return {
        role: v.role,
        imageInfo: { filename: v.filename, order: v.order },
        skus,
        skuItems: skus.map(s => ({ item_code: itemBySku[s] || null, sku: s })),
        sites: [...v.sites].filter(s => siteNames.value.includes(s))
      }
    }).filter(im => im.skus.length)

    orderCount.value = appliedOrderCount.value = Math.max(new Set(allImages.map(i => i.imageInfo?.order || 0)).size, 1)
    await loadAllImages(allImages)
    frappe.show_alert({ message: 'Migrated data from the old system. Review and Upload to Save', indicator: 'green' })
  } catch (e) {
    console.error('Migration failed:', e)
    frappe.show_alert({ message: 'Migration failed', indicator: 'red' })
  } finally {
    isLoadingFromS3.value = false
    s3LoadingProgress.value = { completed: 0, total: 0, current: '' }
  }
}

// Upload state
const isUploading = ref(false)
const uploadComplete = ref(false)
const uploadProgress = ref({ completed: 0, total: 0 })
const currentUpload = ref(null)
const uploadErrors = ref([])
const uploadedFiles = ref([])

// Load state (loading an existing record when its template is selected)
const isLoadingFromS3 = ref(false)
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
           (file.file || file.isOnServer) && // Has an actual image (scaffold slots need an upload)
           (!file.isBroken || file.file) // Not broken OR has replacement file
  })
})

// Product-level rule: every variant of the locked template must have all 4 size images.
// Distinguishes a variant that's in NO image card (`unassigned`) from one that's merely
// missing a size (`incomplete`) so each gets a clearer message.
const variantImageIssues = computed(() => {
  if (!templateItem.value) return []

  // SKUs that appear on any card (regardless of whether the image is uploaded yet).
  const assignedSkus = new Set()
  // Roles present per sku, counting only cards that actually have an image.
  const rolesBySku = {}
  templateVariants.value.forEach(v => { rolesBySku[v.sku] = new Set() })

  files.value.forEach(file => {
    const skuList = file.skus ? file.skus.split(',').map(s => s.trim()).filter(s => s) : []
    skuList.forEach(sku => assignedSkus.add(sku))
    if (!file.role || !(file.file || file.isOnServer)) return
    skuList.forEach(sku => {
      if (rolesBySku[sku]) rolesBySku[sku].add(file.role)
    })
  })

  const issues = []
  templateVariants.value.forEach(v => {
    if (!assignedSkus.has(v.sku)) {
      issues.push({ sku: v.sku, item_code: v.item_code, kind: 'unassigned', missing: [...ROLES] })
      return
    }
    const missing = ROLES.filter(r => !rolesBySku[v.sku].has(r))
    if (missing.length) issues.push({ sku: v.sku, item_code: v.item_code, kind: 'incomplete', missing })
  })
  return issues
})

// Product-level validity: a template is chosen, every variant has all 4 images, AND
// every order is fully filled (valid image count covers all expected slots — so it isn't
// "ready" after just the first order while later orders are still empty/loading).
const productValid = computed(() =>
  !!templateItem.value &&
  files.value.length > 0 &&
  variantImageIssues.value.length === 0 &&
  validationSummary.value.valid >= expectedImageCount.value
)

// Computed property to check if upload is possible
const canUpload = computed(() => {
  // Allow upload if S3 is configured and either:
  // 1. There are no files (metadata-only upload)
  // 2. All files are valid AND the product (every variant) is complete
  if (!isS3Configured.value) return false
  if (files.value.length === 0) return true
  return allFilesValid.value && productValid.value
})

// Computed property to get validation summary
const validationSummary = computed(() => {
  const total = files.value.length
  const valid = files.value.filter(file => 
    file.role &&
    file.skus && file.skus.trim() &&
    file.sites && file.sites.length > 0 &&
    (file.imageOrder >= 0) &&
    (file.file || file.isOnServer) && // Scaffold slots need an uploaded image
    (!file.isBroken || file.file) // Include broken images as invalid unless they have a replacement file
  ).length
  
  return { total, valid, invalid: total - valid }
})

// Selectable sites — Lead Sources that have a Lead Source Domain set.
// Each entry is { name, lead_source_domain }; the stored value is the name.
const siteList = ref([])
const siteNames = computed(() => siteList.value.map(s => s.name))

const loadSites = async () => {
  try {
    const sites = await callBackend('get_sites')
    siteList.value = sites || []
  } catch (error) {
    console.error('Failed to load sites:', error)
  }
}


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
  if (!isS3Configured.value) return // S3 disabled — no uploading
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
        skus: '', // derived comma list of resolved retail SKUs (kept in sync with skuItems)
        skuItems: [], // [{ item_code, sku }]
        newItemCode: '', // transient input for adding an item code
        skuError: '', // transient validation message for the SKU adder
        resolvingItem: false,
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

// Copy a field's value from the changed file to every file AFTER it (not before).
const cascadeForward = (field, changedFile) => {
  // Match by object identity, not name — loaded files can share a (SKU-based) name,
  // which would otherwise make the cascade start above the changed image.
  const index = files.value.indexOf(changedFile)
  if (index === -1) return
  for (let i = index + 1; i < files.value.length; i++) {
    files.value[i][field] = JSON.parse(JSON.stringify(changedFile[field])) // clone per file
  }
}

// Keep file.skus (comma list of resolved retail SKUs) in sync with skuItems.
const syncSkus = (file) => {
  file.skus = (file.skuItems || []).filter(i => i.sku).map(i => i.sku).join(', ')
}

// The SKU grid emitted a new committed list for this image; store + cascade it
// to the images after this one, then refresh their derived `skus`.
const updateSkuItems = (file, items) => {
  file.skuItems = items
  cascadeForward('skuItems', file)
  files.value.forEach(syncSkus)
  markAsModified(file)
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

// Aggregate the upload per SKU: each SKU's item_code, the union of its sites, and
// its images (by order + role). This is the atomic, per-SKU view that is saved to
// the doctype; products are formed by merging these afterwards.
const aggregatePerSku = () => {
  const bySku = {} // sku -> { item_code, sites: Set, images: { [order]: {icon,small,medium,large} } }

  // sku -> item_code (item_code is fixed per SKU)
  const skuToItem = {}
  files.value.forEach(f => (f.skuItems || []).forEach(i => {
    if (i.sku) skuToItem[i.sku] = i.item_code || null
  }))

  files.value.forEach(file => {
    const skuList = file.skus ? file.skus.split(',').map(s => s.trim()).filter(s => s) : []
    if (skuList.length === 0) return

    const order = file.imageOrder !== undefined ? file.imageOrder : 0

    skuList.forEach(sku => {
      if (!bySku[sku]) {
        bySku[sku] = { item_code: skuToItem[sku] || null, sites: new Set(), images: {} }
      }
      file.sites.forEach(site => bySku[sku].sites.add(site))

      if (file.role) {
        if (!bySku[sku].images[order]) {
          bySku[sku].images[order] = { order, icon: null, small: null, medium: null, large: null }
        }
        bySku[sku].images[order][file.role] = `products/${file.role}/${generateS3Filename(file)}`
      }
    })
  })

  return Object.keys(bySku).map(sku => ({
    sku,
    item_code: bySku[sku].item_code,
    sites: [...bySku[sku].sites],
    images: Object.values(bySku[sku].images).sort((a, b) => a.order - b.order)
  }))
}

// Per-FILE records for saving — keeps each image's own sites so they can be
// restored per image (not unioned per product). One entry per uploaded image.
const perFileEntries = () => {
  return files.value
    .filter(file => file.role && file.skus && file.skus.trim())
    .map(file => ({
      role: file.role,
      order: file.imageOrder !== undefined ? file.imageOrder : 0,
      path: `products/${file.role}/${generateS3Filename(file)}`,
      skuItems: (file.skuItems || []).filter(i => i.sku).map(i => ({ item_code: i.item_code || null, sku: i.sku })),
      sites: [...file.sites]
    }))
}

// Merge per-SKU entries that share identical sites AND identical images into a
// single product (productsku lists all those SKUs). Differing entries stay separate.
const mergeProducts = (perSku) => {
  const bySig = {}
  perSku.forEach(entry => {
    const sig = JSON.stringify({ sites: [...entry.sites].sort(), images: entry.images })
    if (!bySig[sig]) {
      bySig[sig] = {
        productsku: [entry.sku],
        sites: entry.sites,
        overrideFullProduct: overrideFullProduct.value,
        images: entry.images
      }
    } else {
      bySig[sig].productsku.push(entry.sku)
    }
  })
  return Object.values(bySig)
}

// Create the S3 metadata ({ products: [...] }) used for Export JSON and validation.
const createS3Metadata = () => {
  return { products: mergeProducts(aggregatePerSku()) }
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
  resetFiles()

  // Reset the order count.
  orderCount.value = 1
  appliedOrderCount.value = 1

  // Clear the locked template + its picker.
  templateItem.value = null
  templateVariants.value = []
  if (templateControl) templateControl.set_value('')
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

// Add an image to a scaffolded (placeholder) card. Keeps the card's preset role
// and SKU; just attaches the uploaded image and turns it into a real file.
const addImageToPlaceholder = async (file, event) => {
  const newFile = event.target.files[0]
  if (!newFile || !newFile.type.startsWith('image/')) return
  try {
    const img = await loadImage(newFile)
    file.file = newFile
    file.width = img.width
    file.height = img.height
    file.type = newFile.type
    const ext = (newFile.name.split('.').pop() || 'jpg').toLowerCase()
    const sku = (file.skus || '').split(',')[0].trim()
    file.name = `${sku}_${file.role}.${ext}`
    if (file.preview) URL.revokeObjectURL(file.preview)
    file.preview = URL.createObjectURL(newFile)
    file.isPlaceholder = false
    file.isModified = true
  } catch (error) {
    console.error('Failed to add placeholder image:', error)
  }
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

    // Only save metadata when every image uploaded and was verified on S3.
    const uploadSucceeded =
      uploadErrors.value.length === 0 &&
      uploadedFiles.value.length === imagesToUpload.length &&
      uploadedFiles.value.every(f => f.verified)

    if (uploadSucceeded) {
      currentUpload.value = {
        filename: 'metadata',
        status: 'Saving metadata...'
      }

      try {
        // Save one record per upload from the per-FILE view, so each image keeps
        // its own sites (restored per image on load).
        await callBackend('save_metadata', {
          files: JSON.stringify(perFileEntries()),
          override_full_product: overrideFullProduct.value ? 1 : 0,
          template_item: templateItem.value || ''
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
    } else {
      // One or more images failed to upload/verify — don't write metadata.
      uploadErrors.value.push({
        id: Date.now(),
        filename: 'metadata',
        message: 'Metadata not saved because one or more images failed to upload.'
      })
    }

    uploadProgress.value.completed = uploadProgress.value.total
    
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

// Shared: fetch each loaded image (via the backend) and add file objects to the editor.
const loadAllImages = async (allImages) => {
  s3LoadingProgress.value.total = allImages.length
  s3LoadingProgress.value.completed = 0

  // Load each image
  for (let i = 0; i < allImages.length; i++) {
    const { role, imageInfo, skus, skuItems, sites } = allImages[i]
      
      s3LoadingProgress.value.current = `Loading ${imageInfo.filename}...`
      
      let fileObj = null
      let isImageBroken = false
      
      try {
        const normalizedImageFilename = normalizeFilename(imageInfo.filename)
        // Full S3 key, e.g. images/products/icon/GEN99989-0002.jpg
        const key = `${s3Config.value.base_prefix}/${role}/${normalizedImageFilename}`

        // Fetch the image bytes through the backend (boto3) — no public bucket / CORS needed.
        const result = await callBackend('get_image', { key })
        if (!result || !result.found) {
          console.warn(`Image not found in S3: ${key}`)
          isImageBroken = true
        } else {
          const contentType = result.content_type || 'image/jpeg'
          const imageBlob = base64ToBlob(result.content, contentType)
          const normalizedFilename = normalizeFilename(imageInfo.originalName || imageInfo.filename)
          const imageFile = new File([imageBlob], normalizedFilename, { type: contentType })

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
              skuItems: (skuItems || []).map(i => ({ ...i })),
              newItemCode: '',
              skuError: '',
              resolvingItem: false,
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
          skuItems: (skuItems || []).map(i => ({ ...i })),
          newItemCode: '',
          skuError: '',
          resolvingItem: false,
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

  autoSortFiles()
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

// Build the top-level template picker (native Frappe Link to Item).
const buildTemplateControl = () => {
  if (!templateRef.value) return
  templateRef.value.innerHTML = ''
  templateControl = frappe.ui.form.make_control({
    parent: templateRef.value,
    render_input: true,
    df: {
      fieldtype: 'Link',
      options: 'Item',
      placeholder: 'Select a product template…',
    },
  })
  templateControl.refresh()
  templateControl.$input.on('change awesomplete-selectcomplete', () => {
    setTimeout(() => {
      const val = templateControl.get_value() || ''
      if (val !== templateItem.value) applyTemplateFromItem(val)
    }, 0)
  })
}

// Load S3 config + selectable sites on mount
onMounted(() => {
  loadS3Config()
  loadSites()
  nextTick(buildTemplateControl)
})

// Reload config (used by the page's "refresh" toolbar action)
const refresh = () => {
  loadS3Config()
  loadSites()
}

defineExpose({ refresh })
</script>
