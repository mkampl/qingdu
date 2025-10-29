// Vocabulary Lists Management

// Load vocabulary lists from storage
async function loadVocabularyLists() {
  const vocabDiv = document.getElementById('vocabularyLists');

  if (!window.AuthState?.user) {
    vocabDiv.innerHTML = '<div style="padding:10px;color:#999;font-size:14px">🔒 Login to access</div>';
    return;
  }

  try {
    const response = await authFetch('/api/vocabulary-lists');

    if (!response.ok) throw new Error('Failed to load lists');

    const lists = await response.json();
    vocabDiv.innerHTML = '';

    // Add "New List" button at the top
    const newListBtn = document.createElement('button');
    newListBtn.className = 'add-btn';
    newListBtn.style.cssText = 'width: 100%; margin-bottom: 10px;';
    newListBtn.innerHTML = '+ New List';
    newListBtn.onclick = openCreateListModal;
    vocabDiv.appendChild(newListBtn);

    // Check if HSK list exists
    const hskExists = lists.some(list => list.type === 'hsk' || list.list_type === 'hsk');

    if (!hskExists) {
      const btn = createGenerateHSKButton();
      vocabDiv.appendChild(btn);
    }

    if (lists.length === 0) {
      const empty = document.createElement('div');
      empty.style.cssText = 'padding:10px;color:#999;font-size:14px';
      empty.textContent = 'No vocabulary lists yet';
      vocabDiv.appendChild(empty);
      return;
    }

    lists.forEach((list) => {
      const wordCount = list.sections.reduce((sum, section) => sum + section.words.length, 0);
      const item = document.createElement('div');
      item.className = 'sidebar-item';

      const icon = list.type === 'hsk' ? '📚' : '📝';
      item.innerHTML = `
        <span class="sidebar-item-icon">${icon}</span>
        <span class="sidebar-item-text">${list.name} (${wordCount} words)</span>
        <button class="icon-btn edit" title="Rename list" onclick="event.stopPropagation(); renameList(${list.id}, '${list.name.replace(/'/g, "\\'")}')">✏️</button>
        <button class="icon-btn delete" title="Delete list" onclick="event.stopPropagation(); deleteVocabularyList(${list.id}, '${list.name.replace(/'/g, "\\'")}')">🗑️</button>
      `;

      item.querySelector('.sidebar-item-text').addEventListener('click', () => {
        viewVocabularyList(list.id);
      });

      vocabDiv.appendChild(item);
    });
  } catch (error) {
    console.error('Failed to load vocabulary lists:', error);
    vocabDiv.innerHTML = '<div style="padding:10px;color:#dc3545;font-size:14px">Error loading lists</div>';
  }
}

// Create generate HSK button
function createGenerateHSKButton() {
  const btn = document.createElement('div');
  btn.className = 'sidebar-item';
  btn.innerHTML = `
    <span class="sidebar-item-icon">⚡</span>
    <span>Generate HSK List</span>
  `;
  btn.addEventListener('click', generateHSKList);
  return btn;
}

// Generate HSK list
async function generateHSKList() {
  if (!confirm('This will load all 11,000+ HSK words. Continue?')) return;
  
  document.getElementById('vocabularyLists').innerHTML = '<div class="loading">Generating HSK list...</div>';
  
  try {
    const vocabResponse = await fetch('/api/get-hsk-vocabulary');
    const vocabData = await vocabResponse.json();
    
    const hskList = {
      name: 'HSK Vocabulary',
      type: 'hsk',
      sections: Array.from({ length: 9 }, (_, i) => ({ name: `HSK ${i + 1}`, words: [] }))
    };
    
    Object.entries(vocabData).forEach(([word, data]) => {
      const level = data.level.replace('new-', '').replace('old-', '').replace('+', '');
      const levelNum = parseInt(level);
      
      if (levelNum >= 1 && levelNum <= 9) {
        hskList.sections[levelNum - 1].words.push({
          hanzi: word,
          pinyin: data.pinyin,
          meaning: data.meaning,
          level: data.level
        });
      }
    });
    
    await authFetch('/api/vocabulary-lists', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(hskList)
    });
    
    loadVocabularyLists();
    alert('HSK list generated successfully!');
  } catch (error) {
    alert('Error: ' + error.message);
    loadVocabularyLists();
  }
}

// View vocabulary list by ID
async function viewVocabularyList(listId) {
  try {
    console.log('viewVocabularyList called with listId:', listId, 'type:', typeof listId);
    const response = await authFetch('/api/vocabulary-lists');
    const lists = await response.json();
    console.log('Fetched lists:', lists.length, 'lists');
    console.log('List IDs:', lists.map(l => ({id: l.id, name: l.name, sections: l.sections.length})));

    const list = lists.find(l => l.id === listId);
    console.log('Found list:', list ? `${list.name} with ${list.sections.length} sections` : 'NOT FOUND');
    if (!list) {
      alert('List not found');
      return;
    }
    
    // Store current list for search
    window.currentVocabList = list;
    
    document.getElementById('listViewTitle').textContent = list.name;
    
    // Create structure with separate containers
    const content = list.sections
      .filter(section => section.words && section.words.length > 0)
      .map(section => createSectionHTML(section))
      .join('');
    
      document.getElementById('listViewContent').innerHTML = `
        <div style="margin-bottom: 20px; display: flex; gap: 10px; align-items: center; flex-wrap: wrap;">
          <input
            type="text"
            id="vocabSearch"
            placeholder="Search words (hanzi, pinyin, or meaning)..."
            style="flex: 1; min-width: 200px; padding: 10px; border: 2px solid #e0e0e0; border-radius: 8px; font-size: 16px;"
          />
          <button class="add-btn" onclick="openAddSectionModal(${listId})">+ Add Section</button>
          <button class="btn btn-secondary" onclick="exportVocabularyList(${listId}, '${list.name.replace(/'/g, "\\'")}')">
            📄 CSV
          </button>
          <button class="btn" onclick="exportVocabularyListAnki(${listId}, '${list.name.replace(/'/g, "\\'")}')">
            📥 Anki (.apkg)
          </button>
        </div>
        <div id="vocabTableContainer">
          ${content || '<p>No words in this list yet. Click "Add Section" to get started.</p>'}
        </div>
      `;
    
    // Attach event listener once
    document.getElementById('vocabSearch').addEventListener('input', (e) => {
      filterVocabWords(e.target.value);
    });
    
    document.getElementById('inputSection').classList.add('collapsed');
    document.getElementById('resultsSection').classList.remove('show');
    document.getElementById('listViewSection').classList.remove('hidden');
    toggleSidebar();
  } catch (error) {
    alert('Failed to load list: ' + error.message);
  }
}

// Filter vocabulary words by search term
function filterVocabWords(searchTerm) {
  if (!window.currentVocabList) return;
  
  const term = searchTerm.toLowerCase().trim();
  const sections = window.currentVocabList.sections;
  const container = document.getElementById('vocabTableContainer');
  
  if (!container) return;
  
  if (!term) {
    // Show all if search is empty
    const content = sections
      .filter(section => section.words && section.words.length > 0)
      .map(section => createSectionHTML(section))
      .join('');
    
    container.innerHTML = content || '<p>No words in this list yet.</p>';
    return;
  }
  
  // Filter sections and words
  const filteredSections = sections
    .map(section => ({
      ...section,
      words: section.words.filter(word => 
        word.hanzi.toLowerCase().includes(term) ||
        word.pinyin.toLowerCase().includes(term) ||
        word.meaning.toLowerCase().includes(term)
      )
    }))
    .filter(section => section.words.length > 0);
  
  const content = filteredSections.length > 0
    ? filteredSections.map(section => createSectionHTML(section)).join('')
    : '<p style="color: #999; padding: 20px;">No matches found</p>';
  
  container.innerHTML = content;
}

// Create section HTML with management buttons
function createSectionHTML(section) {
  // Get current list ID from the window.currentVocabList
  const listId = window.currentVocabList?.id;

  const wordsHTML = section.words
    .map(word => `
      <div class="word-item">
        <div class="word-info">
          <div class="word-hanzi">${word.hanzi}</div>
          <div class="word-pinyin">${word.pinyin}</div>
          <div class="word-meaning">${word.meaning}</div>
          <div class="word-level">${word.level.replace('new-', 'HSK ').replace('+', '+')}</div>
        </div>
        <div class="word-actions">
          <button class="icon-btn edit" title="Edit word"
                  onclick="openWordModal('edit', ${listId}, '${section.name.replace(/'/g, "\\'")}', {
                    hanzi: '${word.hanzi.replace(/'/g, "\\'")}',
                    pinyin: '${word.pinyin.replace(/'/g, "\\'")}',
                    meaning: '${word.meaning.replace(/'/g, "\\'")}',
                    level: '${word.level}'
                  })">✏️</button>
          <button class="icon-btn delete" title="Delete word"
                  onclick="deleteWord(${listId}, '${section.name.replace(/'/g, "\\'")}', '${word.hanzi.replace(/'/g, "\\'")}')">🗑️</button>
        </div>
      </div>
    `)
    .join('');

  return `
    <div class="section-container">
      <div class="section-header" onclick="toggleSection(this)">
        <span><strong>${section.name}</strong> (${section.words.length} words)</span>
        <div style="display: inline-flex; gap: 4px;">
          <button class="icon-btn edit" title="Rename section"
                  onclick="event.stopPropagation(); renameSection(${listId}, '${section.name.replace(/'/g, "\\'")}')">✏️</button>
          <button class="icon-btn delete" title="Delete section"
                  onclick="event.stopPropagation(); deleteSection(${listId}, '${section.name.replace(/'/g, "\\'")}')">🗑️</button>
          <span style="margin-left: 8px;">▼</span>
        </div>
      </div>
      <div class="section-content">
        <button class="add-btn secondary" style="margin: 12px 0;"
                onclick="openWordModal('add', ${listId}, '${section.name.replace(/'/g, "\\'")}')">+ Add Word</button>
        <div>
          ${wordsHTML}
        </div>
      </div>
    </div>
  `;
}

// Toggle section
function toggleSection(header) {
  const content = header.nextElementSibling;
  const isOpen = content.classList.contains('show');
  
  content.classList.toggle('show', !isOpen);
  header.classList.toggle('active', !isOpen);
  header.querySelector('span:last-child').textContent = isOpen ? '▼' : '▲';
}

// Close list view
function closeListView() {
  document.getElementById('listViewSection').classList.add('hidden');
  document.getElementById('resultsSection').classList.add('show');
}

// Save word to list (now functional!)
async function saveWordToList(word, level, pinyin, meaning) {
  // Auto-save if text not saved yet
  if (!window.AppState.currentTextId && window.AppState.currentInputText) {
    if (!confirm('Text must be saved first. Save now?')) {
      return;
    }
    await saveCurrentText();
    // Check if save was successful
    if (!window.AppState.currentTextId) {
      alert('Failed to save text. Please try again.');
      return;
    }
  }
  
  if (!window.AppState.currentTextId) {
    alert('No active text available.');
    return;
  }
  
  try {
    // Get current text info
    const textsResponse = await authFetch('/api/texts');
    const texts = await textsResponse.json();
    const currentText = texts.find(t => t.id === window.AppState.currentTextId);
    
    if (!currentText) {
      alert('Current text not found');
      return;
    }
    
    // Get or create "auto" vocabulary list
    const listsResponse = await authFetch('/api/vocabulary-lists');
    const lists = await listsResponse.json();
    
    let autoList = lists.find(l => l.type === 'auto');
    
    if (!autoList) {
      // Create auto list
      const createResponse = await authFetch('/api/vocabulary-lists', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: 'Vocabulary from Texts',
          type: 'auto',
          sections: []
        })
      });
      
      const result = await createResponse.json();
      
      // The create endpoint returns {id: ..., message: ...}
      // So we can use the ID directly instead of reloading
      if (result.id) {
        autoList = { id: result.id };
      } else {
        // Fallback: reload lists to get the new one
        const newListsResponse = await authFetch('/api/vocabulary-lists');
        const newLists = await newListsResponse.json();
        autoList = newLists.find(l => l.type === 'auto');
      }
    }
    
    if (!autoList) {
      alert('Failed to create vocabulary list');
      return;
    }
    
    // Add word to list
    await authFetch(`/api/vocabulary-lists/${autoList.id}/words`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        section_name: currentText.title,
        hanzi: word,
        pinyin: pinyin,
        meaning: meaning,
        level: level
      })
    });

    await loadVocabularyLists();
    
    alert(`Word "${word}" saved to "${currentText.title}" section!`);
  } catch (error) {
    alert('Failed to save word: ' + error.message);
  }
}
// Delete vocabulary list
async function deleteVocabularyList(listId, listName) {
  if (!confirm(`Delete "${listName}"? This cannot be undone.`)) return;
  
  try {
    await authFetch(`/api/vocabulary-lists/${listId}`, { method: 'DELETE' });
    await loadVocabularyLists();
    alert('List deleted successfully');
  } catch (error) {
    alert('Failed to delete list: ' + error.message);
  }
}
// Export vocabulary as anki deck
async function exportVocabularyList(listId, listName) {
  try {
    const response = await authFetch(`/api/vocabulary-lists/${listId}/export`);
    
    if (!response.ok) {
      throw new Error('Export failed');
    }
    
    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${listName.replace(/ /g, '_')}.csv`;
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);
    
  } catch (error) {
    alert('Failed to export: ' + error.message);
  }
}
// Export vocabulary list as Anki .apkg
async function exportVocabularyListAnki(listId, listName) {
  const btn = event?.target || document.querySelector(`button[onclick*="exportVocabularyListAnki(${listId}"]`);
  
  if (!btn) {
    alert('Button not found');
    return;
  }
  
  const originalText = btn.innerHTML;
  
  try {
    btn.innerHTML = '⏳ Generating...';
    btn.disabled = true;
    
    const response = await authFetch(`/api/vocabulary-lists/${listId}/export-anki`);
    
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Export failed');
    }
    
    // Check for export stats in headers
    const stats = response.headers.get('X-Export-Stats');
    const rateLimited = response.headers.get('X-Rate-Limited') === 'true';
    
    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${listName.replace(/ /g, '_')}.apkg`;
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);
    
    btn.innerHTML = originalText;
    btn.disabled = false;
    
    // Show stats if available
    if (stats) {
      const [total, cached, generated, failed] = stats.split('|').map(Number);
      
      let message = `Export complete!\n\n`;
      message += `📊 Statistics:\n`;
      message += `Total cards: ${total}\n`;
      message += `Audio from cache: ${cached}\n`;
      message += `Audio generated: ${generated}\n`;
      
      if (failed > 0) {
        message += `\n⚠️ AUDIO MISSING: ${failed} cards\n\n`;
        if (rateLimited) {
          message += `❌ Rate limit reached!\n`;
          message += `Google blocked further requests.\n\n`;
        }
        message += `✅ All audio is cached now.\n`;
        message += `Try export again in 12-24 hours.`;
      }
      
      alert(message);
    } else {
      alert('Export complete!');
    }
    
  } catch (error) {
    // Restore button state
    if (btn) {
      btn.innerHTML = originalText;
      btn.disabled = false;
    }
    alert('Failed to export Anki deck: ' + error.message);
  }
}
// Export functions
window.loadVocabularyLists = loadVocabularyLists;
window.viewVocabularyList = viewVocabularyList;
window.toggleSection = toggleSection;
window.closeListView = closeListView;
window.saveWordToList = saveWordToList;
window.deleteVocabularyList = deleteVocabularyList;
window.filterVocabWords = filterVocabWords;
window.exportVocabularyList = exportVocabularyList;
window.exportVocabularyListAnki = exportVocabularyListAnki;