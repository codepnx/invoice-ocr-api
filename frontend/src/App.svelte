<script>
  import { onMount } from 'svelte';

  let file = null;
  let buyer = '';
  let template = 'default_invoice';
  let templates = [];
  let processing = false;
  let result = null;
  let error = null;
  let apiStatus = 'checking...';

  // API base URL - adjust if needed
  const API_BASE = '/api';

  onMount(async () => {
    await checkHealth();
    await loadTemplates();
  });

  async function checkHealth() {
    try {
      const response = await fetch(`${API_BASE}/health`);
      const data = await response.json();
      apiStatus = data.status === 'healthy' ? 'online' : 'offline';
    } catch (err) {
      apiStatus = 'offline';
      console.error('Health check failed:', err);
    }
  }

  async function loadTemplates() {
    try {
      const response = await fetch(`${API_BASE}/templates`);
      const data = await response.json();
      templates = data.templates;
      if (templates.length > 0 && !template) {
        template = templates[0].name;
      }
    } catch (err) {
      console.error('Failed to load templates:', err);
    }
  }

  function handleFileChange(event) {
    const selectedFile = event.target.files[0];
    if (selectedFile) {
      file = selectedFile;
      result = null;
      error = null;
    }
  }

  async function processDocument() {
    if (!file) {
      error = 'Please select a file';
      return;
    }

    processing = true;
    error = null;
    result = null;

    try {
      const formData = new FormData();
      formData.append('file', file);
      if (buyer) {
        formData.append('buyer', buyer);
      }
      formData.append('template', template);

      const response = await fetch(`${API_BASE}/process`, {
        method: 'POST',
        body: formData
      });

      const data = await response.json();

      if (data.success) {
        result = data;
      } else {
        error = data.error || 'Processing failed';
        result = data; // Show raw response if available
      }
    } catch (err) {
      error = `Error: ${err.message}`;
      console.error('Processing error:', err);
    } finally {
      processing = false;
    }
  }

  function formatJSON(obj) {
    return JSON.stringify(obj, null, 2);
  }

  function formatValue(value) {
    if (value === null || value === undefined) {
      return 'N/A';
    }
    if (typeof value === 'object') {
      if (Array.isArray(value)) {
        return JSON.stringify(value, null, 2);
      } else {
        return JSON.stringify(value, null, 2);
      }
    }
    return String(value);
  }

  function clearForm() {
    file = null;
    buyer = '';
    result = null;
    error = null;
    document.getElementById('fileInput').value = '';
  }
</script>

<main>
  <div class="container">
    <header>
      <h1>Bookkeeping Automation</h1>
      <p class="subtitle">Upload invoices and receipts for automated processing</p>
      <div class="status">
        API Status: <span class="status-indicator {apiStatus === 'online' ? 'online' : 'offline'}">
          {apiStatus}
        </span>
      </div>
    </header>

    <div class="card">
      <h2>Upload Document</h2>

      <div class="form-group">
        <label for="fileInput">
          Select Image or PDF
          <span class="hint">(Supported: JPG, PNG, PDF)</span>
        </label>
        <input
          id="fileInput"
          type="file"
          accept=".jpg,.jpeg,.png,.pdf"
          on:change={handleFileChange}
          disabled={processing}
        />
        {#if file}
          <p class="file-info">Selected: {file.name} ({(file.size / 1024).toFixed(1)} KB)</p>
        {/if}
      </div>

      <div class="form-group">
        <label for="buyer">
          Buyer Name (Optional)
          <span class="hint">Helps identify the service provider</span>
        </label>
        <input
          id="buyer"
          type="text"
          bind:value={buyer}
          placeholder="e.g., Acme Corp"
          disabled={processing}
        />
      </div>

      <div class="form-group">
        <label for="template">Prompt Template</label>
        <select id="template" bind:value={template} disabled={processing}>
          {#each templates as tmpl}
            <option value={tmpl.name}>{tmpl.name} - {tmpl.description}</option>
          {/each}
        </select>
      </div>

      <div class="button-group">
        <button
          class="btn btn-primary"
          on:click={processDocument}
          disabled={!file || processing}
        >
          {processing ? 'Processing...' : 'Process Document'}
        </button>
        <button
          class="btn btn-secondary"
          on:click={clearForm}
          disabled={processing}
        >
          Clear
        </button>
      </div>
    </div>

    {#if error}
      <div class="card error-card">
        <h3>Error</h3>
        <p class="error-message">{error}</p>
      </div>
    {/if}

    {#if result}
      <div class="card result-card">
        <h2>Extracted Data</h2>

        {#if result.success && result.data}
          <div class="result-grid">
            {#each Object.entries(result.data) as [key, value]}
              <div class="result-item">
                <span class="result-key">{key}:</span>
                <div class="result-value">
                  {#if typeof value === 'object' && value !== null}
                    <pre class="json-value">{formatValue(value)}</pre>
                  {:else}
                    {formatValue(value)}
                  {/if}
                </div>
              </div>
            {/each}
          </div>

          {#if result.validation_errors && result.validation_errors.length > 0}
            <div class="validation-section">
              <h3 class="validation-title error">Validation Errors</h3>
              <ul class="validation-list error">
                {#each result.validation_errors as error}
                  <li>{error}</li>
                {/each}
              </ul>
            </div>
          {/if}

          {#if result.validation_warnings && result.validation_warnings.length > 0}
            <div class="validation-section">
              <h3 class="validation-title warning">Validation Warnings</h3>
              <ul class="validation-list warning">
                {#each result.validation_warnings as warning}
                  <li>{warning}</li>
                {/each}
              </ul>
            </div>
          {/if}

          <details class="raw-json">
            <summary>View Raw JSON</summary>
            <pre>{formatJSON(result.data)}</pre>
          </details>
        {:else}
          <div class="warning">
            <p>Processing completed but no structured data extracted.</p>
            {#if result.raw_response}
              <details>
                <summary>View Raw Response</summary>
                <pre>{result.raw_response}</pre>
              </details>
            {/if}
          </div>
        {/if}
      </div>
    {/if}
  </div>
</main>

<style>
  :global(body) {
    margin: 0;
    padding: 0;
  }

  main {
    min-height: 100vh;
    padding: 2rem 1rem;
  }

  .container {
    max-width: 800px;
    margin: 0 auto;
  }

  header {
    text-align: center;
    margin-bottom: 2rem;
  }

  h1 {
    color: #333;
    margin: 0 0 0.5rem 0;
    font-size: 2.5rem;
  }

  .subtitle {
    color: #666;
    margin: 0 0 1rem 0;
  }

  .status {
    font-size: 0.9rem;
    color: #666;
  }

  .status-indicator {
    font-weight: 600;
    padding: 0.25rem 0.5rem;
    border-radius: 4px;
  }

  .status-indicator.online {
    color: #22c55e;
    background: #f0fdf4;
  }

  .status-indicator.offline {
    color: #ef4444;
    background: #fef2f2;
  }

  .card {
    background: white;
    border-radius: 8px;
    padding: 2rem;
    margin-bottom: 1.5rem;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  }

  h2 {
    margin: 0 0 1.5rem 0;
    color: #333;
    font-size: 1.5rem;
  }

  .form-group {
    margin-bottom: 1.5rem;
  }

  label {
    display: block;
    margin-bottom: 0.5rem;
    color: #333;
    font-weight: 500;
  }

  .hint {
    color: #999;
    font-weight: 400;
    font-size: 0.9rem;
  }

  input[type="file"],
  input[type="text"],
  select {
    width: 100%;
    padding: 0.75rem;
    border: 1px solid #ddd;
    border-radius: 4px;
    font-size: 1rem;
    box-sizing: border-box;
  }

  input[type="text"]:focus,
  select:focus {
    outline: none;
    border-color: #3b82f6;
  }

  .file-info {
    margin-top: 0.5rem;
    color: #666;
    font-size: 0.9rem;
  }

  .button-group {
    display: flex;
    gap: 1rem;
  }

  .btn {
    padding: 0.75rem 1.5rem;
    border: none;
    border-radius: 4px;
    font-size: 1rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s;
  }

  .btn-primary {
    background: #3b82f6;
    color: white;
  }

  .btn-primary:hover:not(:disabled) {
    background: #2563eb;
  }

  .btn-secondary {
    background: #e5e7eb;
    color: #333;
  }

  .btn-secondary:hover:not(:disabled) {
    background: #d1d5db;
  }

  .btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .error-card {
    border-left: 4px solid #ef4444;
  }

  .error-message {
    color: #dc2626;
    margin: 0;
  }

  .result-card {
    border-left: 4px solid #22c55e;
  }

  .result-grid {
    display: grid;
    gap: 1rem;
    margin-bottom: 1.5rem;
  }

  .result-item {
    display: grid;
    grid-template-columns: 180px 1fr;
    gap: 1rem;
    padding: 0.75rem;
    background: #f9fafb;
    border-radius: 4px;
  }

  .result-key {
    font-weight: 600;
    color: #4b5563;
  }

  .result-value {
    color: #1f2937;
  }

  .json-value {
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 4px;
    padding: 0.5rem;
    font-size: 0.85rem;
    margin: 0;
    color: #334155;
    overflow-x: auto;
  }

  .raw-json {
    margin-top: 1rem;
  }

  summary {
    cursor: pointer;
    color: #3b82f6;
    font-weight: 500;
    padding: 0.5rem 0;
  }

  pre {
    background: #1f2937;
    color: #f3f4f6;
    padding: 1rem;
    border-radius: 4px;
    overflow-x: auto;
    font-size: 0.9rem;
  }

  .warning {
    padding: 1rem;
    background: #fef3c7;
    border-radius: 4px;
    color: #92400e;
  }

  .validation-section {
    margin: 1rem 0;
    padding: 1rem;
    border-radius: 6px;
  }

  .validation-title {
    margin: 0 0 0.5rem 0;
    font-size: 1rem;
    font-weight: 600;
  }

  .validation-title.error {
    color: #dc2626;
  }

  .validation-title.warning {
    color: #d97706;
  }

  .validation-list {
    margin: 0;
    padding-left: 1.5rem;
  }

  .validation-list.error {
    color: #dc2626;
    background: #fef2f2;
    border-left: 3px solid #dc2626;
    padding: 0.75rem 0.75rem 0.75rem 1.5rem;
    margin: 0;
    border-radius: 0 4px 4px 0;
  }

  .validation-list.warning {
    color: #d97706;
    background: #fffbeb;
    border-left: 3px solid #d97706;
    padding: 0.75rem 0.75rem 0.75rem 1.5rem;
    margin: 0;
    border-radius: 0 4px 4px 0;
  }

  .validation-list li {
    margin-bottom: 0.25rem;
  }

  @media (max-width: 640px) {
    .result-item {
      grid-template-columns: 1fr;
      gap: 0.25rem;
    }

    .button-group {
      flex-direction: column;
    }
  }
</style>
