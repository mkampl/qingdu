// Main Application State
const AppState = {
  currentAnalysisData: null,
  currentSentenceText: '',
  currentTextId: null,
  currentInputText: '',
  sidebarOpen: false,
  longPressTimer: null,
};

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
    document.getElementById('listViewSection').classList.add('hidden');
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
  document.getElementById('listViewSection').classList.add('hidden');
  document.getElementById('textInput').value = '';
  document.getElementById('textInput').focus();
  toggleSidebar();
}

// Load texts from localStorage
async function loadTextsFromStorage() {
  if (!AuthState.user) {
      document.getElementById('textsList').innerHTML = 
          '<div style="padding:10px;color:#999;font-size:14px">🔒 Login to access</div>';
      return;
  }
  
  try {
      const response = await authFetch('/api/texts');
      
      if (!response.ok) {
          throw new Error('Failed to load texts');
      }
      
      const texts = await response.json();  // Erst nach ok-Check
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
  } catch (error) {
      console.error('Failed to load texts:', error);
      document.getElementById('textsList').innerHTML = 
          '<div style="padding:10px;color:#dc3545;font-size:14px">Error loading texts</div>';
  }
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
      AppState.currentTextId = texts[index].id;  // <- Schon da
      AppState.currentInputText = texts[index].content;
      
      displayResults(texts[index].analysisData);
      
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
async function saveCurrentText() {
  if (!AppState.currentInputText || !AppState.currentAnalysisData) {
    alert('No text to save');
    return;
  }
  
  const title = AppState.currentInputText.split(/[。！？]/)[0] || 
                AppState.currentInputText.substring(0, 50);
  
  try {
    const response = await authFetch('/api/texts/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ 
        title: title,
        content: AppState.currentInputText,
        analysis_data: AppState.currentAnalysisData 
      })
    });
    
    const data = await response.json();
    AppState.currentTextId = data.id;  // <- NEU: Setze ID nach dem Speichern
    
    document.getElementById('saveTextBtn').disabled = true;
    await loadTextsFromStorage();
    alert('Text saved successfully!');
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
document.addEventListener('click', function(event) {
  const userMenu = document.getElementById('userMenu');
  const dropdown = document.getElementById('userMenuDropdown');
  
  if (userMenu && !userMenu.contains(event.target)) {
      dropdown.classList.remove('show');
  }
});

window.toggleUserMenu = toggleUserMenu;
window.showAdminPanel = function() { window.location.href = '/admin'; };
// Initialize app on page load
window.onload = async function() {
  await initAuth();  // Auth FIRST
  
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
// Export functions to global scope (temporary, will use modules later)
window.toggleSidebar = toggleSidebar;
window.showNewTextInput = showNewTextInput;
window.analyzeText = analyzeText;
window.saveCurrentText = saveCurrentText;
window.clearAll = clearAll;
window.AppState = AppState;