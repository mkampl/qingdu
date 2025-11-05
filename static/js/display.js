// Display and interaction logic for analyzed text

// Store event listeners for cleanup
const eventListenerRegistry = {
  wordListeners: [],
  sentenceListeners: []
};

// Cleanup function to remove all registered event listeners
function cleanupEventListeners() {
  // Remove word click listeners
  eventListenerRegistry.wordListeners.forEach(({ element, handler }) => {
    if (element && element.parentNode) { // Check element still exists
      element.removeEventListener('click', handler);
    }
  });
  eventListenerRegistry.wordListeners = [];

  // Remove sentence listeners (click, mousedown, mouseup, touchstart, touchend)
  eventListenerRegistry.sentenceListeners.forEach(({ element, events }) => {
    if (element && element.parentNode) {
      Object.entries(events).forEach(([eventType, handler]) => {
        element.removeEventListener(eventType, handler);
      });
    }
  });
  eventListenerRegistry.sentenceListeners = [];
}

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

  // Render HTML with progress bar
  const html = `
  <div id="readingProgress" style="position: sticky; top: 0; width: calc(100% + 40px); margin: 0 -20px 15px -20px; height: 20px; background: white; z-index: 10; box-shadow: 0 2px 4px rgba(0,0,0,0.1); display: flex; align-items: center; padding: 0 20px;">
    <div style="width: 100%; height: 4px; background: #e0e0e0; border-radius: 2px;">
      <div id="readingProgressBar" style="height: 100%; width: 0%; background: linear-gradient(90deg, #667eea, #764ba2); border-radius: 2px; transition: width 0.1s;"></div>
    </div>
  </div>
  ${renderSentences(sentences, pinyinLevel)}
`;

  document.getElementById('readingArea').innerHTML = html;

  // Cleanup old listeners before adding new ones
  cleanupEventListeners();

  // Setup interactions
  setupWordInteractions();
  setupSentenceInteractions();

  // Setup reading progress tracking
  setTimeout(setupReadingProgress, 100);

  // Display statistics
  displayStatistics(stats, pinyinLevel);
}

// Listen for settings changes and re-render if text is displayed
window.addEventListener('settingsChanged', (event) => {
  const { key } = event.detail;

  // If pinyin_mode or hsk_version changed and we have analysis data, re-render
  if ((key === 'pinyin_mode' || key === 'hsk_version') && window.AppState?.currentAnalysisData) {
    displayResults(window.AppState.currentAnalysisData);
  }

  // If hsk_version changed, update the legend even if no text is displayed
  if (key === 'hsk_version') {
    const legendElement = document.getElementById('hskLegendContent');
    if (legendElement && typeof displayHSKLegend === 'function') {
      displayHSKLegend();
    }
  }
});

// Build sentences from word array
function buildSentences(words) {
  const sentences = [];
  let currentSentence = [];

  words.forEach(word => {
    // Handle line breaks as sentence boundaries
    if (word.text === '\n') {
      if (currentSentence.length > 0) {
        sentences.push([...currentSentence]);
        currentSentence = [];
      }
      // Add line break as a separate "sentence"
      sentences.push([{ text: '\n', is_linebreak: true }]);
      return;
    }

    currentSentence.push({
      text: word.text,
      is_hsk: word.is_hsk,
      level: word.hsk_level,
      level_new: word.level_new,
      level_old: word.level_old,
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
    // Check if this is a line break
    if (sentence.length === 1 && sentence[0].is_linebreak) {
      return '<br>';
    }

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

  // Get hsk_version setting to determine which level to use for coloring
  const hskVersion = window.SettingsManager?.get('hsk_version') || 'new';

  // Determine which level to use for coloring
  let displayLevel;
  if (hskVersion === 'new') {
    // In new HSK mode: use level_new if available, otherwise fall back to level
    displayLevel = word.level_new || word.level;
  } else {
    // In old HSK mode: use level_old if available
    // If word doesn't have old HSK level, show as unknown
    displayLevel = word.level_old || 'unknown';
  }

  const levelClass = displayLevel.replace(/-/g, '').replace(/\+/g, 'plus');
  const wordLevel = displayLevel === 'unknown' ? 999 :
                    parseInt(displayLevel.replace('new-', '').replace('old-', '').replace('+', ''));

  // Get pinyin_mode setting from SettingsManager
  const pinyinMode = window.SettingsManager?.get('pinyin_mode') || 'auto';

  // Determine whether to show pinyin based on mode
  let showPinyin;
  if (pinyinMode === 'on') {
    showPinyin = true; // Always show
  } else if (pinyinMode === 'off') {
    showPinyin = false; // Never show
  } else {
    // 'auto' - show if word level is above user level
    showPinyin = wordLevel > pinyinLevel;
  }

  const source = word.translation_source || (word.level === 'unknown' ? 'mymemory' : 'hsk');

  const baseAttrs = `
    class="hsk-word ${levelClass}${showPinyin ? ' pinyin-above' : ''}"
    data-pinyin="${word.pinyin}"
    data-word="${escapeHtml(word.text)}"
    data-level="${word.level}"
    data-level-new="${word.level_new || ''}"
    data-level-old="${word.level_old || ''}"
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
    const handler = (e) => {
      e.stopPropagation();

      const word = wordEl.getAttribute('data-word');
      const level = wordEl.getAttribute('data-level');
      const levelNew = wordEl.getAttribute('data-level-new');
      const levelOld = wordEl.getAttribute('data-level-old');
      const pinyin = wordEl.getAttribute('data-pinyin');
      const meaning = wordEl.getAttribute('data-meaning');
      const source = wordEl.getAttribute('data-source');

      showWordInfo(word, level, pinyin, meaning, source, levelNew, levelOld);
    };

    wordEl.addEventListener('click', handler);

    // Register for cleanup
    eventListenerRegistry.wordListeners.push({ element: wordEl, handler });
  });
}

// Setup sentence interactions (click and long-press)
function setupSentenceInteractions() {
  const sentenceWrappers = document.querySelectorAll('.sentence-wrapper');

  sentenceWrappers.forEach(wrapper => {
    let pressTimer;
    let longPressHappened = false;

    // Create handler functions that will be registered
    const mousedownHandler = (e) => {
      longPressHappened = false;
      pressTimer = setTimeout(() => {
        longPressHappened = true;
        const sentenceText = wrapper.getAttribute('data-sentence');
        if (sentenceText) {
          showSentence(unescapeHtml(sentenceText));
        }
      }, 500);
    };

    const mouseupHandler = () => {
      clearTimeout(pressTimer);
    };

    const clickHandler = (e) => {
      clearTimeout(pressTimer);
      if (!longPressHappened && e.target === wrapper) {
        const sentenceText = wrapper.getAttribute('data-sentence');
        if (sentenceText) {
          showSentence(unescapeHtml(sentenceText));
        }
      }
      setTimeout(() => { longPressHappened = false; }, 100);
    };

    const touchstartHandler = (e) => {
      longPressHappened = false;
      pressTimer = setTimeout(() => {
        longPressHappened = true;
        const sentenceText = wrapper.getAttribute('data-sentence');
        if (sentenceText) {
          showSentence(unescapeHtml(sentenceText));
        }
      }, 500);
    };

    const touchendHandler = () => {
      clearTimeout(pressTimer);
    };

    // Add event listeners
    wrapper.addEventListener('mousedown', mousedownHandler);
    wrapper.addEventListener('mouseup', mouseupHandler);
    wrapper.addEventListener('click', clickHandler);
    wrapper.addEventListener('touchstart', touchstartHandler);
    wrapper.addEventListener('touchend', touchendHandler);

    // Register all handlers for cleanup
    eventListenerRegistry.sentenceListeners.push({
      element: wrapper,
      events: {
        'mousedown': mousedownHandler,
        'mouseup': mouseupHandler,
        'click': clickHandler,
        'touchstart': touchstartHandler,
        'touchend': touchendHandler
      }
    });
  });
}

// Show word information panel
function showWordInfo(word, level, pinyin, meaning, source, levelNew, levelOld) {
  let levelText;

  // Build transparent display of both levels
  const parts = [];
  if (levelNew) {
    parts.push(`New HSK ${levelNew.replace('new-', '').replace('+', '+')}`);
  }
  if (levelOld) {
    parts.push(`Old HSK ${levelOld.replace('old-', '')}`);
  }

  if (parts.length === 2) {
    levelText = `${parts[0]} (${parts[1]})`;
  } else if (parts.length === 1) {
    levelText = parts[0];
  } else if (level === 'unknown') {
    // Truly unknown word (not in any HSK system)
    levelText = 'Unknown (Online lookup)';
  } else {
    // Fallback to original level
    levelText = level.replace('new-', 'HSK ').replace('old-', 'HSK ').replace('+', '+');
  }

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

  // Also display HSK legend
  displayHSKLegend();
}

// Display HSK level color legend
function displayHSKLegend() {
  const hskVersion = window.SettingsManager?.get('hsk_version') || 'new';

  let levels;
  let prefix;

  if (hskVersion === 'old') {
    levels = [1, 2, 3, 4, 5, 6];
    prefix = 'old-';
  } else {
    levels = [1, 2, 3, 4, 5, 6, 7, '7+'];
    prefix = 'new-';
  }

  const legendItems = levels.map(level => {
    const cssClass = `${prefix}${level}`.replace('+', 'plus');
    const displayLevel = hskVersion === 'old' ? `Old HSK ${level}` : `New HSK ${level}`;

    return `
      <div style="display: flex; align-items: center; margin-bottom: 8px;">
        <span class="hsk-word ${cssClass}" style="padding: 4px 12px; border-radius: 4px; min-width: 60px; text-align: center; font-weight: 500;">样本</span>
        <span style="margin-left: 10px; color: #666;">${displayLevel}</span>
      </div>
    `;
  }).join('');

  const html = `
    <div style="font-size: 13px;">
      <p style="color: #999; margin-bottom: 10px;">Color coding based on ${hskVersion === 'old' ? 'Old HSK (Pre-2021)' : 'New HSK (2021)'}</p>
      ${legendItems}
    </div>
  `;

  document.getElementById('hskLegendContent').innerHTML = html;
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
// Flag to prevent saving during restore
let isRestoringProgress = false;

// Track reading progress
function setupReadingProgress() {
  const readingArea = document.getElementById('readingArea');
  const progressBar = document.getElementById('readingProgressBar');
  
  if (!readingArea || !progressBar) return;
  
  readingArea.addEventListener('scroll', () => {
    console.log('SCROLL EVENT - isRestoring:', isRestoringProgress); // DEBUG
    
    // Don't save if we're currently restoring
    if (isRestoringProgress) {
      console.log('Skipping scroll event during restore'); // DEBUG
      return;
    }
    
    const scrollTop = readingArea.scrollTop;
    const scrollHeight = readingArea.scrollHeight - readingArea.clientHeight;
    
    if (scrollHeight <= 0) {
      progressBar.style.width = '100%';
      return;
    }
    
    const progress = (scrollTop / scrollHeight) * 100;
    console.log('Setting bar to:', progress); // DEBUG
    progressBar.style.width = `${Math.min(progress, 100)}%`;
    
    if (window.AppState?.currentTextId && progress >= 1) {
      saveReadingProgress(window.AppState.currentTextId, progress);
    }
  });
  
  restoreReadingProgress();
}


// Debounced save to avoid too many API calls
let saveProgressTimeout;
function saveReadingProgress(textId, progress) {
  clearTimeout(saveProgressTimeout);
  saveProgressTimeout = setTimeout(async () => {
    try {
      await authFetch(`/api/texts/${textId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reading_progress: Math.round(progress) })
      });
    } catch (e) {
      // Silent fail - progress tracking is not critical
      console.log('Progress save failed:', e);
    }
  }, 2000); // Save every 2 seconds max
}

// Restore reading progress when loading text
function restoreReadingProgress() {
  const progress = window.AppState?.currentReadingProgress;
  console.log('=== RESTORE called with progress:', progress); // DEBUG
  
  if (!progress || progress === 0) {
    return;
  }
  
  const readingArea = document.getElementById('readingArea');
  if (!readingArea) return;
  
  isRestoringProgress = true;
  console.log('Set isRestoringProgress = true'); // DEBUG
  
  setTimeout(() => {
    const progressBar = document.getElementById('readingProgressBar');
    const scrollHeight = readingArea.scrollHeight - readingArea.clientHeight;
    const scrollTo = (progress / 100) * scrollHeight;
    
    console.log('About to scroll to:', scrollTo, 'and set bar to:', progress); // DEBUG
    
    readingArea.scrollTop = scrollTo;
    
    if (progressBar) {
      progressBar.style.width = `${progress}%`;
      console.log('Bar width set to:', progress); // DEBUG
    }
    
    setTimeout(() => {
      isRestoringProgress = false;
      console.log('Set isRestoringProgress = false'); // DEBUG
    }, 1000);
  }, 400);
}

// Export
window.setupReadingProgress = setupReadingProgress;
// Export functions
window.displayResults = displayResults;
window.showWordInfo = showWordInfo;
window.showSentence = showSentence;
window.speakWord = speakWord;
window.speakSentence = speakSentence;
window.cleanupEventListeners = cleanupEventListeners;
