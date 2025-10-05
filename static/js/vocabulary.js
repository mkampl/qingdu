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
    
    // Check if HSK list exists
    const hskExists = lists.some(list => list.type === 'hsk' || list.list_type === 'hsk');
    
    if (!hskExists) {
      const btn = createGenerateHSKButton();
      vocabDiv.appendChild(btn);
    }
    
    if (lists.length === 0 && hskExists) {
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
    const response = await authFetch('/api/vocabulary-lists');
    const lists = await response.json();
    
    const list = lists.find(l => l.id === listId);
    if (!list) {
      alert('List not found');
      return;
    }
    
    document.getElementById('listViewTitle').textContent = list.name;
    
    const content = list.sections
      .filter(section => section.words && section.words.length > 0)
      .map(section => createSectionHTML(section))
      .join('');
    
    document.getElementById('listViewContent').innerHTML = content || '<p>No words in this list yet.</p>';
    document.getElementById('inputSection').classList.add('collapsed');
    document.getElementById('resultsSection').classList.remove('show');
    document.getElementById('listViewSection').classList.remove('hidden');
    toggleSidebar();
  } catch (error) {
    alert('Failed to load list: ' + error.message);
  }
}

// Create section HTML
function createSectionHTML(section) {
  const wordsTable = section.words
    .map(word => `
      <tr>
        <td class="hanzi">${word.hanzi}</td>
        <td>${word.pinyin}</td>
        <td>${word.meaning}</td>
        <td>${word.level.replace('new-', 'HSK ').replace('+', '+')}</td>
      </tr>
    `)
    .join('');
  
  return `
    <div class="section-container">
      <div class="section-header" onclick="toggleSection(this)">
        <span><strong>${section.name}</strong> (${section.words.length} words)</span>
        <span>▼</span>
      </div>
      <div class="section-content">
        <table class="word-table">
          <thead>
            <tr>
              <th>Hanzi</th>
              <th>Pinyin</th>
              <th>Meaning</th>
              <th>Level</th>
            </tr>
          </thead>
          <tbody>
            ${wordsTable}
          </tbody>
        </table>
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
  if (!window.AppState.currentTextId) {
    alert('No active text. Please save the text first.');
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
    
    // Fix: use 'type' instead of 'list_type' (matches API response)
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
    
    alert(`Word "${word}" saved to "${currentText.title}" section!`);
  } catch (error) {
    alert('Failed to save word: ' + error.message);
  }
}

// Export functions
window.loadVocabularyLists = loadVocabularyLists;
window.viewVocabularyList = viewVocabularyList;
window.toggleSection = toggleSection;
window.closeListView = closeListView;
window.saveWordToList = saveWordToList;