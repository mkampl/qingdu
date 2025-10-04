// Vocabulary Lists Management

// Load vocabulary lists from storage
function loadVocabularyLists() {
  const lists = JSON.parse(localStorage.getItem('qingdu_lists') || '[]');
  const vocabDiv = document.getElementById('vocabularyLists');
  vocabDiv.innerHTML = '';
  
  // Check if HSK list exists
  const hskExists = lists.some(list => list.type === 'hsk');
  
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
  
  lists.forEach((list, index) => {
    const item = createVocabListItem(list, index);
    vocabDiv.appendChild(item);
  });
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

// Create vocabulary list item
function createVocabListItem(list, index) {
  const wordCount = list.sections.reduce((sum, section) => sum + section.words.length, 0);
  
  const item = document.createElement('div');
  item.className = 'sidebar-item';
  
  const icon = list.type === 'hsk' ? '📚' : '📝';
  item.innerHTML = `
    <span class="sidebar-item-icon">${icon}</span>
    <span class="sidebar-item-text">${list.name} (${wordCount} words)</span>
  `;
  
  item.querySelector('.sidebar-item-text').addEventListener('click', () => {
    viewVocabularyList(index);
  });
  
  return item;
}

// Generate HSK list
async function generateHSKList() {
  if (!confirm('This will load all 11,000+ HSK words. Continue?')) return;
  
  document.getElementById('vocabularyLists').innerHTML = 
    '<div class="loading">Generating HSK list...</div>';
  
  try {
    const response = await fetch('/api/get-hsk-vocabulary');
    if (!response.ok) throw new Error('Failed to fetch vocabulary');
    
    const vocabData = await response.json();
    const lists = JSON.parse(localStorage.getItem('qingdu_lists') || '[]');
    
    const hskList = {
      id: Date.now(),
      name: 'HSK Vocabulary',
      type: 'hsk',
      sections: Array.from({ length: 9 }, (_, i) => ({
        name: `HSK ${i + 1}`,
        words: []
      }))
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
    
    lists.push(hskList);
    localStorage.setItem('qingdu_lists', JSON.stringify(lists));
    loadVocabularyLists();
    alert('HSK list generated successfully!');
  } catch (error) {
    alert(`Error: ${error.message}`);
    loadVocabularyLists();
  }
}

// View vocabulary list
function viewVocabularyList(index) {
  const lists = JSON.parse(localStorage.getItem('qingdu_lists') || '[]');
  if (!lists[index]) return;
  
  const list = lists[index];
  document.getElementById('listViewTitle').textContent = list.name;
  
  const content = list.sections
    .filter(section => section.words.length > 0)
    .map(section => createSectionHTML(section))
    .join('');
  
  document.getElementById('listViewContent').innerHTML = content;
  document.getElementById('inputSection').classList.add('collapsed');
  document.getElementById('resultsSection').classList.remove('show');
  document.getElementById('listViewSection').classList.remove('hidden');
  toggleSidebar();
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

// Save word to list
function saveWordToList(word, level, pinyin, meaning) {
  if (!window.AppState?.currentTextId) {
    alert('No text active');
    return;
  }
  
  const lists = JSON.parse(localStorage.getItem('qingdu_lists') || '[]');
  let vocabList = lists.find(list => list.type === 'auto');
  
  if (!vocabList) {
    vocabList = {
      id: Date.now(),
      name: 'Vocabulary from Texts',
      type: 'auto',
      sections: []
    };
    lists.push(vocabList);
  }
  
  const texts = JSON.parse(localStorage.getItem('qingdu_texts') || '[]');
  const currentText = texts.find(text => text.id === window.AppState.currentTextId);
  
  if (!currentText) {
    alert('Current text not found');
    return;
  }
  
  let section = vocabList.sections.find(s => s.name === currentText.title);
  
  if (!section) {
    section = { name: currentText.title, words: [] };
    vocabList.sections.push(section);
  }
  
  if (section.words.some(w => w.hanzi === word)) {
    alert('Word already in list!');
    return;
  }
  
  section.words.push({ hanzi: word, pinyin, meaning, level });
  localStorage.setItem('qingdu_lists', JSON.stringify(lists));
  alert(`Word saved to "${currentText.title}" section!`);
}

// Export functions
window.loadVocabularyLists = loadVocabularyLists;
window.viewVocabularyList = viewVocabularyList;
window.toggleSection = toggleSection;
window.closeListView = closeListView;
window.saveWordToList = saveWordToList;
