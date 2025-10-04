// Main Application State
const AppState = {
  currentAnalysisData: null,
  currentSentenceText: '',
  currentTextId: null,
  currentInputText: '',
  sidebarOpen: false,
  longPressTimer: null,
};

// Initialize app on page load
document.addEventListener('DOMContentLoaded', async () => {
  await loadVocabularyStats();
  loadTextsFromStorage();
  loadVocabularyLists();
  setupEventListeners();
});

// Load vocabulary statistics
async function loadVocabularyStats() {
  try {
    const response = await fetch('/api/vocabulary-stats');
    const data = await response.json();
    const vocabCount = document.getElementById('vocabCount');
    vocabCount.textContent = data.loaded 
      ? `${data.count.toLocaleString()} words loaded` 
      : 'Loading...';
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
  document.getElementById('inputSection').classList.remove('collapsed');
  document.getElementById('resultsSection').classList.remove('show');
  document.getElementById('textInput').value = '';
  document.getElementById('textInput').focus();
  toggleSidebar();
}

// Load texts from localStorage
function loadTextsFromStorage() {
  const texts = JSON.parse(localStorage.getItem('qingdu_texts') || '[]');
  const textsList = document.getElementById('textsList');
  textsList.innerHTML = '';
  
  if (texts.length === 0) {
    textsList.innerHTML = '<div style="padding:10px;color:#999;font-size:14px">No saved texts yet</div>';
    return;
  }
  
  texts.forEach((text, index) => {
    const item = createTextListItem(text, index);
    textsList.appendChild(item);
  });
}

// Create text list item
function createTextListItem(text, index) {
  const item = document.createElement('div');
  item.className = 'sidebar-item';
  
  const truncatedTitle = text.title.length > 30 
    ? text.title.substring(0, 30) + '...' 
    : text.title;
  
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

// Save text to storage
function saveTextToStorage(textId, title, content, analysisData) {
  const texts = JSON.parse(localStorage.getItem('qingdu_texts') || '[]');
  
  // Check for duplicates
  if (texts.some(text => text.content === content)) {
    alert('This text has already been saved!');
    return;
  }
  
  texts.unshift({ 
    id: textId, 
    title, 
    content, 
    date: new Date().toISOString(), 
    analysisData 
  });
  
  localStorage.setItem('qingdu_texts', JSON.stringify(texts));
  loadTextsFromStorage();
}

// Load text
function loadText(index) {
  const texts = JSON.parse(localStorage.getItem('qingdu_texts') || '[]');
  
  if (!texts[index]) return;
  
  AppState.currentAnalysisData = texts[index].analysisData;
  AppState.currentTextId = texts[index].id;
  AppState.currentInputText = texts[index].content;
  
  displayResults(texts[index].analysisData);
  
  document.getElementById('inputSection').classList.add('collapsed');
  document.getElementById('resultsSection').classList.add('show');
  document.getElementById('listViewSection').classList.add('hidden');
  document.getElementById('saveTextBtn').disabled = true;
  
  toggleSidebar();
}

// Delete text
function deleteText(index) {
  if (!confirm('Delete this text?')) return;
  
  const texts = JSON.parse(localStorage.getItem('qingdu_texts') || '[]');
  texts.splice(index, 1);
  localStorage.setItem('qingdu_texts', JSON.stringify(texts));
  loadTextsFromStorage();
}

// Analyze text
async function analyzeText() {
  const text = document.getElementById('textInput').value.trim();
  
  if (!text) {
    alert('Please enter some text!');
    return;
  }
  
  AppState.currentInputText = text;
  AppState.currentTextId = null;
  
  const readingArea = document.getElementById('readingArea');
  readingArea.innerHTML = '<div class="loading">Analyzing...</div>';
  
  document.getElementById('resultsSection').classList.add('show');
  document.getElementById('saveTextBtn').disabled = false;
  
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
    displayResults(data);
    document.getElementById('inputSection').classList.add('collapsed');
  } catch (error) {
    readingArea.innerHTML = `<div style="color:#e74c3c">Error: ${error.message}</div>`;
    console.error('Analysis failed:', error);
  }
}

// Save current text
function saveCurrentText() {
  if (!AppState.currentInputText || !AppState.currentAnalysisData) {
    alert('No text to save');
    return;
  }
  
  const title = AppState.currentInputText.split(/[。！？]/)[0] || 
                AppState.currentInputText.substring(0, 50);
  const textId = Date.now();
  AppState.currentTextId = textId;
  
  saveTextToStorage(textId, title, AppState.currentInputText, AppState.currentAnalysisData);
  document.getElementById('saveTextBtn').disabled = true;
  alert('Text saved successfully!');
}

// Clear all
function clearAll() {
  document.getElementById('textInput').value = '';
  document.getElementById('inputSection').classList.remove('collapsed');
  document.getElementById('resultsSection').classList.remove('show');
  AppState.currentAnalysisData = null;
  AppState.currentSentenceText = '';
}

// Export functions to global scope (temporary, will use modules later)
window.toggleSidebar = toggleSidebar;
window.showNewTextInput = showNewTextInput;
window.analyzeText = analyzeText;
window.saveCurrentText = saveCurrentText;
window.clearAll = clearAll;
window.AppState = AppState;