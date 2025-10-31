// Main Application State
const AppState = {
  currentAnalysisData: null,
  currentSentenceText: '',
  currentTextId: null,
  currentInputText: '',
  currentReadingProgress: 0, // NEW
  sidebarOpen: false,
  longPressTimer: null,
};

// Load vocabulary statistics
let vocabLoadRetries = 0;
const MAX_VOCAB_RETRIES = 30; // Poll for up to ~30 seconds

async function loadVocabularyStats() {
  try {
    const response = await fetch('/api/vocabulary-stats');
    const data = await response.json();
    const vocabCount = document.getElementById('vocabCount');

    if (data.loaded) {
      vocabCount.textContent = `${data.count.toLocaleString()} words loaded`;
      vocabLoadRetries = 0; // Reset retry counter on success
    } else {
      // Still loading - show loading message and retry
      vocabCount.textContent = 'Loading...';

      if (vocabLoadRetries < MAX_VOCAB_RETRIES) {
        vocabLoadRetries++;
        // Retry after 1 second
        setTimeout(loadVocabularyStats, 1000);
      } else {
        vocabCount.textContent = 'Loading failed - check logs';
        console.error('Vocabulary loading timeout after', MAX_VOCAB_RETRIES, 'attempts');
      }
    }
  } catch (error) {
    document.getElementById('vocabCount').textContent = 'Error loading';
    console.error('Failed to load vocabulary stats:', error);
  }
}

// Setup all event listeners
function setupEventListeners() {
  // Input placeholder click
  document.getElementById('inputPlaceholder').addEventListener('click', () => {
    document.getElementById('inputSection').classList.remove('collapsed');
    document.getElementById('resultsSection').classList.remove('show');
    document.getElementById('listViewSection').classList.add('hidden');
    document.getElementById('savedTextsSection').classList.add('hidden');
    document.getElementById('textInput').focus();
  });

  // Overlay click (close sidebar)
  document.getElementById('overlay').addEventListener('click', toggleSidebar);
}

// Toggle sidebar
function toggleSidebar() {
  AppState.sidebarOpen = !AppState.sidebarOpen;
  document.getElementById('sidebar').classList.toggle('open', AppState.sidebarOpen);
  document.getElementById('overlay').classList.toggle('show', AppState.sidebarOpen);
}

// Show new text input
function showNewTextInput() {
  // Clear current state
  AppState.currentTextId = null;
  AppState.currentInputText = '';
  AppState.currentAnalysisData = null;
  AppState.currentReadingProgress = 0;
  currentTags = [];

  // Reset UI
  document.getElementById('textInput').value = '';
  document.getElementById('currentTextTitle').textContent = 'Reading Text';
  document.getElementById('inputSection').classList.remove('collapsed');
  document.getElementById('resultsSection').classList.remove('show');
  document.getElementById('listViewSection').classList.add('hidden');
  document.getElementById('savedTextsSection').classList.add('hidden');

  // Hide tags button and dialog
  showTagsButton(false);
  document.getElementById('tagsDialog').style.display = 'none';
  tagsDialogOpen = false;

  document.getElementById('textInput').focus();
  toggleSidebar();
}

// Load texts from localStorage
// Load texts from storage - simplified for new UI
async function loadTextsFromStorage() {
  // This function is now only called for backward compatibility
  // The actual texts loading happens in showSavedTextsView()
  // We can make this a no-op since we removed the sidebar list
  return;
}

// Save text to storage
async function saveTextToStorage(textId, title, content, analysisData) {
  if (!AuthState.user) {
    alert('Please login to save texts');
    return;
  }

  try {
    await authFetch('/api/texts/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title, content, analysis_data: analysisData })
    });
    await loadTextsFromStorage();
  } catch (error) {
    alert('Failed to save text: ' + error.message);
  }
}
// Create text list item
function createTextListItem(text, index) {
  const item = document.createElement('div');
  item.className = 'sidebar-item';

  const truncatedTitle = text.title && text.title.length > 30
    ? text.title.substring(0, 30) + '...'
    : (text.title || 'Untitled');

  item.innerHTML = `
    <span class="sidebar-item-icon">📄</span>
    <span class="sidebar-item-text">${truncatedTitle}</span>
    <button class="sidebar-item-delete" title="Delete text">🗑️</button>
  `;

  // Click handler for loading text
  item.querySelector('.sidebar-item-text').addEventListener('click', () => {
    loadText(index);
  });

  // Click handler for delete button
  item.querySelector('.sidebar-item-delete').addEventListener('click', (e) => {
    e.stopPropagation();
    deleteText(index);
  });

  return item;
}
// Load text
async function loadText(index) {
  try {
    const response = await authFetch('/api/texts');
    const texts = await response.json();

    if (texts[index]) {
      AppState.currentAnalysisData = texts[index].analysisData;
      AppState.currentTextId = texts[index].id;
      AppState.currentInputText = texts[index].content;

      // Store reading progress for restoration
      AppState.currentReadingProgress = texts[index].reading_progress || 0;

      displayResults(texts[index].analysisData);

      // Update title
      document.getElementById('currentTextTitle').textContent = texts[index].title || 'Untitled';

      // Load tags and show button
      const tags = texts[index].tags ? JSON.parse(texts[index].tags) : [];
      displayTags(tags);
      showTagsButton(true);
      tagsDialogOpen = false;
      document.getElementById('tagsDialog').style.display = 'none';

      document.getElementById('inputSection').classList.add('collapsed');
      document.getElementById('resultsSection').classList.add('show');
      document.getElementById('listViewSection').classList.add('hidden');
      document.getElementById('saveTextBtn').disabled = true;

      toggleSidebar();
    }
  } catch (error) {
    alert('Failed to load text: ' + error.message);
  }
}
// Start inline title editing
function startTitleEdit(textId, currentTitle, spanElement) {
  const input = document.createElement('input');
  input.type = 'text';
  input.value = currentTitle || 'Untitled';
  input.className = 'title-edit-input';
  input.style.cssText = 'width: 100%; padding: 5px; border: 2px solid #667eea; border-radius: 5px; font-size: 14px;';

  // Replace span with input
  const parent = spanElement.parentElement;
  parent.replaceChild(input, spanElement);
  input.focus();
  input.select();

  // Save on Enter
  input.addEventListener('keydown', async (e) => {
    if (e.key === 'Enter') {
      await saveTitleEdit(textId, input.value, parent);
    } else if (e.key === 'Escape') {
      await loadTextsFromStorage(); // Cancel - reload list
    }
  });

  // Save on blur (click outside)
  input.addEventListener('blur', async () => {
    await saveTitleEdit(textId, input.value, parent);
  });
}

// Save edited title
async function saveTitleEdit(textId, newTitle, parentElement) {
  if (!newTitle.trim()) {
    alert('Title cannot be empty');
    await loadTextsFromStorage();
    return;
  }

  try {
    await authFetch(`/api/texts/${textId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: newTitle })
    });

    // Update UI in results section if this text is currently displayed
    if (AppState.currentTextId === textId) {
      // Could add visual indicator here
    }

    await loadTextsFromStorage();
  } catch (error) {
    alert('Failed to update title: ' + error.message);
    await loadTextsFromStorage();
  }
}
// Load text
async function loadText(index) {
  try {
    const response = await authFetch('/api/texts');
    const texts = await response.json();

    if (texts[index]) {
      AppState.currentAnalysisData = texts[index].analysisData;
      AppState.currentTextId = texts[index].id;
      AppState.currentInputText = texts[index].content;

      displayResults(texts[index].analysisData);

      // Update title in header
      document.getElementById('currentTextTitle').textContent = texts[index].title || 'Untitled';

      // Load and display tags
      const tags = texts[index].tags ? JSON.parse(texts[index].tags) : [];
      displayTags(tags);
      showTagsSection(true);

      document.getElementById('inputSection').classList.add('collapsed');
      document.getElementById('resultsSection').classList.add('show');
      document.getElementById('listViewSection').classList.add('hidden');
      document.getElementById('saveTextBtn').disabled = true;

      toggleSidebar();
    }
  } catch (error) {
    alert('Failed to load text: ' + error.message);
  }
}

// Delete text
async function deleteText(index) {
  if (!confirm('Delete this text?')) return;

  try {
    const response = await authFetch('/api/texts');
    const texts = await response.json();

    if (texts[index]) {
      await authFetch(`/api/texts/${texts[index].id}`, { method: 'DELETE' });
      await loadTextsFromStorage();
    }
  } catch (error) {
    alert('Failed to delete text: ' + error.message);
  }
}

// Simulate progress bar animation
function simulateProgress(progressBar, progressText, targetPercent, duration) {
  const startPercent = parseInt(progressBar.style.width) || 0;
  const increment = (targetPercent - startPercent) / (duration / 50);
  let currentPercent = startPercent;

  const interval = setInterval(() => {
    currentPercent += increment;
    if (currentPercent >= targetPercent) {
      currentPercent = targetPercent;
      clearInterval(interval);
    }
    progressBar.style.width = currentPercent + '%';
    progressText.textContent = Math.round(currentPercent) + '%';
  }, 50);

  return interval;
}

// Analyze text
async function analyzeText() {
  const text = document.getElementById('textInput').value.trim();

  if (!text) {
    alert('Please enter some text!');
    return;
  }

  // Reset state for new text
  AppState.currentInputText = text;
  AppState.currentTextId = null;
  AppState.currentReadingProgress = 0;
  currentTags = [];

  // Hide tags until text is saved
  showTagsButton(false);
  document.getElementById('tagsDialog').style.display = 'none';

  // Show loading overlay and reset progress
  const progressBar = document.getElementById('analysisProgressBar');
  const progressText = document.getElementById('progressText');
  progressBar.style.width = '0%';
  progressText.textContent = '0%';
  document.getElementById('loadingOverlay').classList.add('show');

  // Simulate progress: 0% -> 20% quickly
  let progressInterval = simulateProgress(progressBar, progressText, 20, 500);

  // Then 20% -> 75% over 2 seconds
  setTimeout(() => {
    progressInterval = simulateProgress(progressBar, progressText, 75, 2000);
  }, 500);

  try {
    const response = await fetch('/api/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text })
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const data = await response.json();
    AppState.currentAnalysisData = data;

    // Jump to 100%
    clearInterval(progressInterval);
    progressBar.style.width = '100%';
    progressText.textContent = '100%';

    // Wait a moment to show 100%, then hide overlay
    await new Promise(resolve => setTimeout(resolve, 300));
    document.getElementById('loadingOverlay').classList.remove('show');

    // Now show results
    displayResults(data);
    document.getElementById('resultsSection').classList.add('show');
    document.getElementById('inputSection').classList.add('collapsed');
    document.getElementById('saveTextBtn').disabled = false;

    // Set title to first sentence
    const firstSentence = text.split(/[。！？\n]/)[0] || text.substring(0, 50);
    document.getElementById('currentTextTitle').textContent = firstSentence;

  } catch (error) {
    // Clear progress interval and hide loading overlay on error
    clearInterval(progressInterval);
    document.getElementById('loadingOverlay').classList.remove('show');

    // Show error in results section
    const readingArea = document.getElementById('readingArea');
    readingArea.innerHTML = `<div style="color:#e74c3c">Error: ${error.message}</div>`;
    document.getElementById('resultsSection').classList.add('show');

    console.error('Analysis failed:', error);
  }
}

// Save current text
async function saveCurrentText() {
  if (!AppState.currentInputText || !AppState.currentAnalysisData) {
    alert('No text to save');
    return;
  }

  const title = AppState.currentInputText.split(/[。！？\n]/)[0] ||
    AppState.currentInputText.substring(0, 50);

  // Auto-generate HSK level tag
  const estimatedLevel = AppState.currentAnalysisData.statistics?.estimated_level || 'Unknown';
  const autoTags = [estimatedLevel]; // e.g., "HSK 3"

  try {
    let response;

    if (AppState.currentTextId) {
      // Update existing text
      response = await authFetch(`/api/texts/${AppState.currentTextId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: title,
          content: AppState.currentInputText,
          analysis_data: AppState.currentAnalysisData,
          tags: autoTags
        })
      });
      alert('Text updated successfully!');
    } else {
      // Create new text
      response = await authFetch('/api/texts/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: title,
          content: AppState.currentInputText,
          analysis_data: AppState.currentAnalysisData,
          tags: autoTags
        })
      });
      alert('Text saved successfully!');
    }

    const data = await response.json();
    if (!AppState.currentTextId) {
      AppState.currentTextId = data.id;
    }

    // Update current tags and display
    currentTags = autoTags;
    displayTags(currentTags);
    showTagsButton(true);

    document.getElementById('saveTextBtn').disabled = true;
    await loadTextsFromStorage();
  } catch (error) {
    alert('Failed to save: ' + error.message);
  }
}

// Clear all
function clearAll() {
  document.getElementById('textInput').value = '';
  document.getElementById('inputSection').classList.remove('collapsed');
  document.getElementById('resultsSection').classList.remove('show');
  AppState.currentAnalysisData = null;
  AppState.currentSentenceText = '';
}
function toggleUserMenu() {
  const dropdown = document.getElementById('userMenuDropdown');
  dropdown.classList.toggle('show');
}

// Close dropdown when clicking outside
document.addEventListener('click', function (event) {
  const userMenu = document.getElementById('userMenu');
  const dropdown = document.getElementById('userMenuDropdown');

  if (userMenu && !userMenu.contains(event.target)) {
    dropdown.classList.remove('show');
  }
});

window.toggleUserMenu = toggleUserMenu;
window.showAdminPanel = function () { window.location.href = '/admin'; };
// Initialize app on page load
window.onload = async function () {
  await initAuth();  // Auth FIRST

  // Check for invitation token in URL (only if not already logged in)
  if (!AuthState.user) {
    await checkInviteToken();
  }

  // Load vocab stats
  fetch('/api/vocabulary-stats')
    .then(r => r.json())
    .then(d => {
      document.getElementById('vocabCount').textContent =
        d.loaded ? d.count.toLocaleString() + ' words loaded' : 'Loading...';
    });

  // Setup event listeners (synchronous, no await needed)
  setupEventListeners();

  // Load user data if authenticated
  if (AuthState.user) {
    await loadTextsFromStorage();
    await loadVocabularyLists();
  }
};
// Current tags for active text
let currentTags = [];
let tagsDialogOpen = false;

// Show/hide tags section
function showTagsSection(show) {
  const section = document.getElementById('tagsSection');
  if (section) {
    section.style.display = show ? 'block' : 'none';
  }
}

// Toggle tags dialog
function toggleTagsDialog() {
  tagsDialogOpen = !tagsDialogOpen;
  const dialog = document.getElementById('tagsDialog');
  if (dialog) {
    dialog.style.display = tagsDialogOpen ? 'block' : 'none';
    if (tagsDialogOpen) {
      document.getElementById('tagInput').focus();
    }
  }
}

// Show/hide tags button
function showTagsButton(show) {
  const btn = document.getElementById('tagsToggleBtn');
  if (btn) {
    btn.style.display = show ? 'inline-block' : 'none';
  }
}

// Update tags count badge
function updateTagsCount() {
  const countSpan = document.getElementById('tagsCount');
  if (countSpan) {
    countSpan.textContent = currentTags.length > 0 ? `(${currentTags.length})` : '';
  }
}

// Display tags
function displayTags(tags) {
  currentTags = tags || [];
  const display = document.getElementById('tagsDisplay');

  if (!display) return;

  if (currentTags.length === 0) {
    display.innerHTML = '<span style="color: #999; font-size: 12px;">No tags yet</span>';
  } else {
    display.innerHTML = currentTags.map(tag => `
      <span style="background: linear-gradient(135deg, #667eea, #764ba2); color: white; 
                   padding: 5px 12px; border-radius: 15px; font-size: 13px; display: inline-flex; 
                   align-items: center; gap: 8px;">
        ${tag}
        <button onclick="removeTag('${tag}')" 
                style="background: none; border: none; color: white; cursor: pointer; 
                       font-size: 16px; padding: 0; line-height: 1;">
          ×
        </button>
      </span>
    `).join('');
  }

  updateTagsCount();
}

// Add tag
async function addTag() {
  const input = document.getElementById('tagInput');
  const tag = input.value.trim();

  if (!tag) return;

  if (currentTags.includes(tag)) {
    alert('Tag already exists');
    input.value = '';
    return;
  }

  if (!AppState.currentTextId) {
    alert('Please save the text first');
    return;
  }

  currentTags.push(tag);

  try {
    await authFetch(`/api/texts/${AppState.currentTextId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tags: currentTags })
    });

    displayTags(currentTags);
    input.value = '';
    await loadTextsFromStorage();
  } catch (error) {
    alert('Failed to add tag: ' + error.message);
    currentTags.pop();
  }
}

// Remove tag
async function removeTag(tag) {
  if (!AppState.currentTextId) return;

  currentTags = currentTags.filter(t => t !== tag);

  try {
    await authFetch(`/api/texts/${AppState.currentTextId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tags: currentTags })
    });

    displayTags(currentTags);
    await loadTextsFromStorage();
  } catch (error) {
    alert('Failed to remove tag: ' + error.message);
  }
}
// Edit current text title in header
function editCurrentTextTitle() {
  if (!AppState.currentTextId) return;

  const titleElement = document.getElementById('currentTextTitle');
  const currentTitle = titleElement.textContent;

  const input = document.createElement('input');
  input.type = 'text';
  input.value = currentTitle;
  input.style.cssText = 'flex: 1; padding: 8px; border: 2px solid #667eea; border-radius: 5px; font-size: 18px; font-weight: bold;';

  titleElement.replaceWith(input);
  input.focus();
  input.select();

  const saveTitle = async () => {
    const newTitle = input.value.trim();
    if (!newTitle) {
      alert('Title cannot be empty');
      const h3 = document.createElement('h3');
      h3.id = 'currentTextTitle';
      h3.ondblclick = editCurrentTextTitle;
      h3.style.cssText = 'cursor: pointer; flex: 1;';
      h3.title = 'Double-click to edit';
      h3.textContent = currentTitle;
      input.replaceWith(h3);
      return;
    }

    try {
      await authFetch(`/api/texts/${AppState.currentTextId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: newTitle })
      });

      const h3 = document.createElement('h3');
      h3.id = 'currentTextTitle';
      h3.ondblclick = editCurrentTextTitle;
      h3.style.cssText = 'cursor: pointer; flex: 1;';
      h3.title = 'Double-click to edit';
      h3.textContent = newTitle;
      input.replaceWith(h3);

      await loadTextsFromStorage(); // Update sidebar
    } catch (error) {
      alert('Failed to update title: ' + error.message);
    }
  };

  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') saveTitle();
    if (e.key === 'Escape') {
      const h3 = document.createElement('h3');
      h3.id = 'currentTextTitle';
      h3.ondblclick = editCurrentTextTitle;
      h3.style.cssText = 'cursor: pointer; flex: 1;';
      h3.title = 'Double-click to edit';
      h3.textContent = currentTitle;
      input.replaceWith(h3);
    }
  });

  input.addEventListener('blur', saveTitle);
}
// Show saved texts view
async function showSavedTextsView() {
  if (!AuthState.user) {
    alert('Please login to view saved texts');
    return;
  }

  try {
    const response = await authFetch('/api/texts');
    if (!response.ok) throw new Error('Failed to load texts');

    const texts = await response.json();
    allTexts = texts;

    renderSavedTextsTable(texts);

    document.getElementById('inputSection').classList.add('collapsed');
    document.getElementById('resultsSection').classList.remove('show');
    document.getElementById('listViewSection').classList.add('hidden');
    document.getElementById('savedTextsSection').classList.remove('hidden');

    toggleSidebar();
  } catch (error) {
    alert('Failed to load texts: ' + error.message);
  }
}

// Close saved texts view
function closeSavedTextsView() {
  document.getElementById('savedTextsSection').classList.add('hidden');
}

// Render saved texts as cards (works for both desktop and mobile)
function renderSavedTextsTable(texts) {
  const content = document.getElementById('savedTextsContent');
  
  if (texts.length === 0) {
      content.innerHTML = '<p style="text-align: center; color: #999; padding: 40px;">No saved texts yet</p>';
      return;
  }
  
  const cardsHTML = texts.map((text, index) => {
      const date = new Date(text.date || text.createdAt).toLocaleDateString();
      let tags = [];
      try {
          tags = text.tags ? JSON.parse(text.tags) : [];
      } catch (e) {}
      
      const tagsHTML = tags.length > 0
          ? tags.map(tag => `<span class="text-tag">${tag}</span>`).join('')
          : '<span class="text-tag no-tag">No tags</span>';
      
      return `
          <div class="saved-text-card">
              <div class="card-header">
                  <h4>${text.title || 'Untitled'}</h4>
                  <span class="text-date">${date}</span>
              </div>
              <div class="text-tags">${tagsHTML}</div>
              <div class="text-actions">
                  <button class="btn" onclick="loadTextFromView(${index})">Open</button>
                  <button class="btn btn-secondary" onclick="editTextFromView(${index})">Edit</button>
                  <button class="btn btn-secondary" onclick="deleteTextFromView(${index})">Delete</button>
              </div>
          </div>
      `;
  }).join('');
  
  content.innerHTML = `<div class="saved-texts-grid">${cardsHTML}</div>`;
}

// Filter saved texts
function filterSavedTexts(searchTerm) {
  const term = searchTerm.toLowerCase().trim();

  if (!term) {
    renderSavedTextsTable(allTexts);
    return;
  }

  const filtered = allTexts.filter(text => {
    const titleMatch = text.title && text.title.toLowerCase().includes(term);

    let tagsMatch = false;
    if (text.tags) {
      try {
        const tags = JSON.parse(text.tags);
        tagsMatch = tags.some(tag => tag.toLowerCase().includes(term));
      } catch (e) { }
    }

    return titleMatch || tagsMatch;
  });

  renderSavedTextsTable(filtered);
}

// Load text from saved texts view
async function loadTextFromView(index) {
  const text = allTexts[index];
  if (!text) return;

  AppState.currentAnalysisData = text.analysisData;
  AppState.currentTextId = text.id;
  AppState.currentInputText = text.content;
  AppState.currentReadingProgress = text.reading_progress || 0; // NEW

  displayResults(text.analysisData);

  document.getElementById('currentTextTitle').textContent = text.title || 'Untitled';

  const tags = text.tags ? JSON.parse(text.tags) : [];
  displayTags(tags);
  showTagsButton(true);

  document.getElementById('inputSection').classList.add('collapsed');
  document.getElementById('resultsSection').classList.add('show');
  document.getElementById('savedTextsSection').classList.add('hidden');
  document.getElementById('saveTextBtn').disabled = true;
}

// Edit text from saved texts view
async function editTextFromView(index) {
  const text = allTexts[index];
  if (!text) return;

  // Load text into input area for editing
  document.getElementById('textInput').value = text.content;

  // Store the text ID and title for updating after re-analysis
  AppState.currentTextId = text.id;
  AppState.currentInputText = text.content;

  // Show input section
  document.getElementById('inputSection').classList.remove('collapsed');
  document.getElementById('resultsSection').classList.remove('show');
  document.getElementById('savedTextsSection').classList.add('hidden');
  document.getElementById('textInput').focus();
}

// Delete text from saved texts view
async function deleteTextFromView(index) {
  if (!confirm('Delete this text? This cannot be undone.')) return;

  const text = allTexts[index];

  try {
    await authFetch(`/api/texts/${text.id}`, { method: 'DELETE' });
    allTexts.splice(index, 1);
    renderSavedTextsTable(allTexts);
    alert('Text deleted');
  } catch (error) {
    alert('Failed to delete: ' + error.message);
  }
}
// Settings Modal Functions
function openSettingsModal() {
  const modal = document.getElementById('settingsModal');
  const select = document.getElementById('pinyinModeSelect');

  // Load current pinyin mode
  const currentMode = window.SettingsManager.get('pinyin_mode');
  select.value = currentMode;

  modal.classList.add('show');
}

function closeSettingsModal() {
  document.getElementById('settingsModal').classList.remove('show');
}

function changePinyinMode(mode) {
  window.SettingsManager.update('pinyin_mode', mode);
}

// Invitations Modal Functions
async function showInvitationsModal() {
  const modal = document.getElementById('invitationsModal');
  modal.classList.add('show');
  await loadInvitations();
}

function closeInvitationsModal() {
  document.getElementById('invitationsModal').classList.remove('show');
}

async function loadInvitations() {
  try {
    const response = await authFetch('/api/invitations/my-invitations');
    const data = await response.json();

    // Update quota display
    const quotaDisplay = document.getElementById('inviteQuotaDisplay');
    quotaDisplay.textContent = `${data.quota.remaining}/${data.quota.total}`;

    // Enable/disable generate button
    const generateBtn = document.getElementById('generateInviteBtn');
    if (data.quota.remaining <= 0) {
      generateBtn.disabled = true;
      generateBtn.textContent = '❌ Quota Exhausted';
    } else {
      generateBtn.disabled = false;
      generateBtn.textContent = '✨ Generate Invite Link';
    }

    // Render invitations list
    const listContainer = document.getElementById('invitationsList');

    if (data.invitations.length === 0) {
      listContainer.innerHTML = '<p style="text-align: center; color: #999; padding: 20px;">No invitations yet</p>';
      return;
    }

    const invitationsHTML = data.invitations.map(inv => {
      const statusColor = inv.status === 'claimed' ? '#28a745' : (inv.status === 'expired' ? '#dc3545' : '#ffc107');
      const statusText = inv.status === 'claimed' ? `✓ Claimed by ${inv.claimed_by}` : (inv.status === 'expired' ? '✗ Expired' : '⏳ Pending');

      const inviteUrl = `${window.location.origin}/?invite=${inv.full_token}`;

      return `
        <div style="border: 1px solid #e0e0e0; border-radius: 8px; padding: 15px; margin-bottom: 10px; background: white;">
          <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 10px;">
            <div>
              <span style="font-family: monospace; font-size: 13px; background: #f0f0f0; padding: 4px 8px; border-radius: 4px;">
                ...${inv.token}
              </span>
              <div style="margin-top: 5px;">
                <span style="color: ${statusColor}; font-weight: 500; font-size: 13px;">${statusText}</span>
              </div>
            </div>
            ${inv.status === 'pending' ? `
              <button class="btn btn-secondary" style="padding: 6px 12px; font-size: 13px;" onclick="copyInviteLink('${inviteUrl}')">
                📋 Copy Link
              </button>
            ` : ''}
          </div>
          <div style="font-size: 12px; color: #666;">
            Created: ${new Date(inv.created_at).toLocaleDateString()}
            ${inv.claimed_at ? ` • Claimed: ${new Date(inv.claimed_at).toLocaleDateString()}` : ''}
            ${inv.status === 'pending' ? ` • Expires: ${new Date(inv.expires_at).toLocaleDateString()}` : ''}
          </div>
        </div>
      `;
    }).join('');

    listContainer.innerHTML = invitationsHTML;
  } catch (error) {
    alert('Failed to load invitations: ' + error.message);
  }
}

async function generateInvitation() {
  try {
    const response = await authFetch('/api/invitations/generate', {
      method: 'POST'
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to generate invitation');
    }

    const data = await response.json();

    // Show success message and copy link
    await copyInviteLink(data.invite_url);
    alert(`Invitation link generated!\nRemaining quota: ${data.remaining_quota}`);

    // Reload invitations list
    await loadInvitations();
  } catch (error) {
    alert(error.message);
  }
}

async function copyInviteLink(url) {
  try {
    await navigator.clipboard.writeText(url);
    alert('Invitation link copied to clipboard!');
  } catch (error) {
    // Fallback for older browsers
    const textarea = document.createElement('textarea');
    textarea.value = url;
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand('copy');
    document.body.removeChild(textarea);
    alert('Invitation link copied to clipboard!');
  }
}

// Export functions to global scope (temporary, will use modules later)
window.toggleSidebar = toggleSidebar;
window.showNewTextInput = showNewTextInput;
window.analyzeText = analyzeText;
window.saveCurrentText = saveCurrentText;
window.clearAll = clearAll;
window.AppState = AppState;
window.startTitleEdit = startTitleEdit;
window.saveTitleEdit = saveTitleEdit;
window.addTag = addTag;
window.removeTag = removeTag;
window.editCurrentTextTitle = editCurrentTextTitle;
window.toggleTagsDialog = toggleTagsDialog;
window.showSavedTextsView = showSavedTextsView;
window.closeSavedTextsView = closeSavedTextsView;
window.filterSavedTexts = filterSavedTexts;
window.loadTextFromView = loadTextFromView;
window.editTextFromView = editTextFromView;
window.deleteTextFromView = deleteTextFromView;
window.openSettingsModal = openSettingsModal;
window.closeSettingsModal = closeSettingsModal;
window.changePinyinMode = changePinyinMode;
window.showInvitationsModal = showInvitationsModal;
window.closeInvitationsModal = closeInvitationsModal;
window.generateInvitation = generateInvitation;
window.copyInviteLink = copyInviteLink;