// Display and interaction logic for analyzed text

// Display analysis results
function displayResults(data) {
  if (!data?.words || !data?.statistics) {
    console.error('Invalid data structure:', data);
    return;
  }
  
  const stats = data.statistics;
  const estimatedLevelNum = parseInt(stats.estimated_level.replace('HSK ', ''));
  const pinyinLevel = estimatedLevelNum;
  
  // Build sentences from words
  const sentences = buildSentences(data.words);
  
  // Render HTML
  const html = renderSentences(sentences, pinyinLevel);
  document.getElementById('readingArea').innerHTML = html;
  
  // Setup interactions
  setupWordInteractions();
  setupSentenceInteractions();
  
  // Display statistics
  displayStatistics(stats, pinyinLevel);
}

// Build sentences from word array
function buildSentences(words) {
  const sentences = [];
  let currentSentence = [];
  
  words.forEach(word => {
    currentSentence.push({
      text: word.text,
      is_hsk: word.is_hsk,
      level: word.hsk_level,
      pinyin: word.pinyin,
      meaning: word.meaning,
      translation_source: word.translation_source
    });
    
    if (word.text.match(/[。！？]/)) {
      sentences.push([...currentSentence]);
      currentSentence = [];
    }
  });
  
  if (currentSentence.length > 0) {
    sentences.push(currentSentence);
  }
  
  return sentences;
}

// Render sentences as HTML
function renderSentences(sentences, pinyinLevel) {
  return sentences.map(sentence => {
    const sentenceText = sentence.map(w => w.text).join('');
    const escaped = escapeHtml(sentenceText);
    
    const wordsHtml = sentence.map(word => renderWord(word, pinyinLevel)).join('');
    
    return `<span class="sentence-wrapper" data-sentence="${escaped}">${wordsHtml}</span>`;
  }).join('');
}

// Render individual word
function renderWord(word, pinyinLevel) {
  if (!word.is_hsk) {
    return word.text;
  }
  
  const levelClass = word.level.replace(/-/g, '').replace(/\+/g, 'plus');
  const wordLevel = word.level === 'unknown' ? 999 : 
                    parseInt(word.level.replace('new-', '').replace('+', ''));
  const showPinyin = wordLevel > pinyinLevel;
  
  const source = word.translation_source || (word.level === 'unknown' ? 'mymemory' : 'hsk');
  
  const baseAttrs = `
    class="hsk-word ${levelClass}${showPinyin ? ' pinyin-above' : ''}"
    data-pinyin="${word.pinyin}"
    data-word="${escapeHtml(word.text)}"
    data-level="${word.level}"
    data-meaning="${escapeHtml(word.meaning)}"
    data-source="${source}"
    title="${word.pinyin}"
  `.trim();
  
  return `<span ${baseAttrs}>${word.text}</span>`;
}

// Setup word click interactions
function setupWordInteractions() {
  const hskWords = document.querySelectorAll('.hsk-word');
  
  hskWords.forEach(wordEl => {
    wordEl.addEventListener('click', (e) => {
      e.stopPropagation();
      
      const word = wordEl.getAttribute('data-word');
      const level = wordEl.getAttribute('data-level');
      const pinyin = wordEl.getAttribute('data-pinyin');
      const meaning = wordEl.getAttribute('data-meaning');
      const source = wordEl.getAttribute('data-source');
      
      showWordInfo(word, level, pinyin, meaning, source);
    });
  });
}

// Setup sentence interactions (click and long-press)
function setupSentenceInteractions() {
  const sentenceWrappers = document.querySelectorAll('.sentence-wrapper');
  
  sentenceWrappers.forEach(wrapper => {
    let pressTimer;
    let longPressHappened = false;
    
    // Mouse events
    wrapper.addEventListener('mousedown', (e) => {
      longPressHappened = false;
      pressTimer = setTimeout(() => {
        longPressHappened = true;
        const sentenceText = wrapper.getAttribute('data-sentence');
        if (sentenceText) {
          showSentence(unescapeHtml(sentenceText));
        }
      }, 500);
    });
    
    wrapper.addEventListener('mouseup', () => {
      clearTimeout(pressTimer);
    });
    
    wrapper.addEventListener('click', (e) => {
      clearTimeout(pressTimer);
      if (!longPressHappened && e.target === wrapper) {
        const sentenceText = wrapper.getAttribute('data-sentence');
        if (sentenceText) {
          showSentence(unescapeHtml(sentenceText));
        }
      }
      setTimeout(() => { longPressHappened = false; }, 100);
    });
    
    // Touch events
    wrapper.addEventListener('touchstart', (e) => {
      longPressHappened = false;
      pressTimer = setTimeout(() => {
        longPressHappened = true;
        const sentenceText = wrapper.getAttribute('data-sentence');
        if (sentenceText) {
          showSentence(unescapeHtml(sentenceText));
        }
      }, 500);
    });
    
    wrapper.addEventListener('touchend', () => {
      clearTimeout(pressTimer);
    });
  });
}

// Show word information panel
function showWordInfo(word, level, pinyin, meaning, source) {
  const displayLevel = level.replace('new-', 'HSK ').replace('+', '+');
  const levelText = level === 'unknown' ? 'Unknown (Online lookup)' : displayLevel;
  
  const sourceTag = createSourceTag(source);
  
  const html = `
    <div style="display:flex;justify-content:space-between;align-items:center">
      <h4>${word} <span style="color:#667eea">${levelText}</span>${sourceTag}</h4>
      <div>
        <button class="tts-btn" onclick="speakWord('${escapeHtml(word)}')">🔊 Play</button>
        <button class="btn" style="margin:0 0 0 10px;padding:8px 16px;font-size:14px" 
                onclick="saveWordToList('${escapeHtml(word)}','${escapeHtml(level)}','${escapeHtml(pinyin)}','${escapeHtml(meaning)}')">
          Save to List
        </button>
      </div>
    </div>
    <p><strong>Pinyin:</strong> ${pinyin}</p>
    <p><strong>Meaning:</strong> ${meaning}</p>
  `;
  
  document.getElementById('wordInfo').innerHTML = html;
  document.getElementById('wordInfo').style.display = 'block';
  document.getElementById('sentenceInfo').style.display = 'none';
}

// Show sentence translation panel
async function showSentence(sentence) {
  window.AppState.currentSentenceText = sentence;
  
  document.getElementById('sentenceText').innerHTML = `<strong>Chinese:</strong> ${sentence}`;
  document.getElementById('sentenceTranslation').innerHTML = 'Translating...';
  document.getElementById('sentenceInfo').style.display = 'block';
  document.getElementById('wordInfo').style.display = 'none';
  
  try {
    const response = await fetch('/api/translate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: sentence, target_lang: 'en' })
    });
    
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    
    const data = await response.json();
    const sourceTag = createSourceTag(data.source, data.cached);
    
    document.getElementById('sentenceTranslation').innerHTML = 
      `<strong>English:</strong> ${data.translation}${sourceTag}`;
  } catch (error) {
    document.getElementById('sentenceTranslation').innerHTML = 
      `<span style="color:#e74c3c">Error: ${error.message}</span>`;
    console.error('Translation error:', error);
  }
}

// Display statistics
function displayStatistics(stats, pinyinLevel) {
  const distribution = Object.entries(stats.hsk_distribution)
    .filter(([_, count]) => count > 0)
    .map(([key, count]) => `${key.toUpperCase()}: ${count}`)
    .join(', ');
  
  const html = `
    <p><strong>Characters:</strong> ${stats.total_characters}</p>
    <p><strong>Words:</strong> ${stats.total_words}</p>
    <p><strong>HSK Words:</strong> ${stats.hsk_words}</p>
    <p><strong>Estimated Level:</strong> ${stats.estimated_level} (Pinyin for HSK ${pinyinLevel + 1}+)</p>
    <p><strong>Distribution:</strong> ${distribution}</p>
  `;
  
  document.getElementById('statsContent').innerHTML = html;
}

// Create source tag
function createSourceTag(source, cached = false) {
  if (!source || source === 'null' || source === '') return '';
  
  const sourceLabels = {
    'deepl': '🟢 DeepL',
    'google': '🔵 Google',
    'mymemory': '🟡 MyMemory',
    'hsk-chars': '📚 HSK',
    'hsk': '📚 HSK'
  };
  
  const label = sourceLabels[source] || source;
  const cacheText = cached ? ' - cached' : '';
  
  return `<span style="font-size:11px;color:#666;margin-left:8px">(${label}${cacheText})</span>`;
}

// Text-to-speech
function speakWord(text) {
  const cleanText = unescapeHtml(text);
  const audio = new Audio(`/api/tts/${encodeURIComponent(cleanText)}`);
  
  audio.onerror = () => alert('TTS failed');
  audio.play().catch(error => alert(`Error: ${error.message}`));
}

// Speak sentence
function speakSentence() {
  if (window.AppState?.currentSentenceText) {
    speakWord(window.AppState.currentSentenceText);
  }
}

// HTML escape/unescape utilities
function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

function unescapeHtml(text) {
  const div = document.createElement('div');
  div.innerHTML = text;
  return div.textContent;
}

// Export functions
window.displayResults = displayResults;
window.showWordInfo = showWordInfo;
window.showSentence = showSentence;
window.speakWord = speakWord;
window.speakSentence = speakSentence;
