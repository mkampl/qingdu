// Vocabulary Management - CRUD operations for lists, sections, and words

// State
let currentListId = null;
let currentSectionName = null;
let wordModalMode = 'add'; // 'add' or 'edit'
let editingWord = null;

// ==================== MODAL MANAGEMENT ====================

function openCreateListModal() {
  document.getElementById('createListModal').classList.add('show');
  document.getElementById('newListName').focus();
}

function closeCreateListModal() {
  document.getElementById('createListModal').classList.remove('show');
  document.getElementById('newListName').value = '';
}

function openAddSectionModal(listId) {
  currentListId = listId;
  document.getElementById('addSectionModal').classList.add('show');
  document.getElementById('newSectionName').focus();
}

function closeAddSectionModal() {
  document.getElementById('addSectionModal').classList.remove('show');
  document.getElementById('newSectionName').value = '';
  currentListId = null;
}

function openWordModal(mode = 'add', listId, sectionName, word = null) {
  wordModalMode = mode;
  currentListId = listId;
  currentSectionName = sectionName;
  editingWord = word;

  const modal = document.getElementById('wordModal');
  const title = document.getElementById('wordModalTitle');

  if (mode === 'edit' && word) {
    title.textContent = 'Edit Word';
    document.getElementById('wordHanzi').value = word.hanzi;
    document.getElementById('wordMeaning').value = word.meaning;
  } else {
    title.textContent = 'Add Word';
    document.getElementById('wordHanzi').value = '';
    document.getElementById('wordMeaning').value = '';
  }

  modal.classList.add('show');
  document.getElementById('wordHanzi').focus();
}

function closeWordModal() {
  document.getElementById('wordModal').classList.remove('show');
  currentListId = null;
  currentSectionName = null;
  editingWord = null;
  wordModalMode = 'add';
}

// Close modals on Escape key
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    closeCreateListModal();
    closeAddSectionModal();
    closeWordModal();
  }
});

// Close modals on overlay click
document.querySelectorAll('.modal-overlay').forEach(overlay => {
  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) {
      overlay.classList.remove('show');
    }
  });
});

// ==================== LIST MANAGEMENT ====================

async function createNewList() {
  const name = document.getElementById('newListName').value.trim();

  if (!name) {
    alert('Please enter a list name');
    return;
  }

  try {
    const response = await authFetch('/api/vocabulary-lists', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: name,
        type: 'custom',
        sections: []
      })
    });

    if (response.ok) {
      closeCreateListModal();
      await loadVocabularyLists();
      alert(`List "${name}" created successfully!`);
    } else {
      const error = await response.json();
      alert(`Error: ${error.detail || 'Failed to create list'}`);
    }
  } catch (error) {
    console.error('Error creating list:', error);
    alert('Failed to create list');
  }
}

async function renameList(listId, oldName) {
  const newName = prompt('Enter new list name:', oldName);

  if (!newName || newName === oldName) {
    return;
  }

  try {
    const response = await authFetch(`/api/vocabulary-lists/${listId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: newName })
    });

    if (response.ok) {
      await loadVocabularyLists();

      // Update list view title if this list is currently open
      const titleEl = document.getElementById('listViewTitle');
      if (titleEl && titleEl.textContent === oldName) {
        titleEl.textContent = newName;
      }
    } else {
      const error = await response.json();
      alert(`Error: ${error.detail || 'Failed to rename list'}`);
    }
  } catch (error) {
    console.error('Error renaming list:', error);
    alert('Failed to rename list');
  }
}

// ==================== SECTION MANAGEMENT ====================

async function addNewSection() {
  const name = document.getElementById('newSectionName').value.trim();

  if (!name) {
    alert('Please enter a section name');
    return;
  }

  if (!currentListId) {
    alert('No list selected');
    return;
  }

  // Save listId before closing modal (which sets currentListId to null)
  const listId = currentListId;

  try {
    const response = await authFetch(`/api/vocabulary-lists/${listId}/sections`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: name })
    });

    if (response.ok) {
      const result = await response.json();
      console.log('Section added successfully:', result);
      closeAddSectionModal();
      console.log('Now reloading list with ID:', listId);
      await viewVocabularyList(listId);
    } else {
      const error = await response.json();
      console.error('Error adding section:', error);
      alert(`Error: ${error.detail || 'Failed to add section'}`);
    }
  } catch (error) {
    console.error('Error adding section:', error);
    alert('Failed to add section');
  }
}

async function renameSection(listId, oldName) {
  const newName = prompt('Enter new section name:', oldName);

  if (!newName || newName === oldName) {
    return;
  }

  try {
    const response = await authFetch(`/api/vocabulary-lists/${listId}/sections`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        old_name: oldName,
        new_name: newName
      })
    });

    if (response.ok) {
      await viewVocabularyList(listId);
    } else {
      const error = await response.json();
      alert(`Error: ${error.detail || 'Failed to rename section'}`);
    }
  } catch (error) {
    console.error('Error renaming section:', error);
    alert('Failed to rename section');
  }
}

async function deleteSection(listId, sectionName) {
  if (!confirm(`Delete section "${sectionName}"? This will delete all words in this section.`)) {
    return;
  }

  try {
    const response = await authFetch(
      `/api/vocabulary-lists/${listId}/sections/${encodeURIComponent(sectionName)}`,
      { method: 'DELETE' }
    );

    if (response.ok) {
      const result = await response.json();
      await viewVocabularyList(listId);
      alert(`Section deleted (${result.word_count} words removed)`);
    } else {
      const error = await response.json();
      alert(`Error: ${error.detail || 'Failed to delete section'}`);
    }
  } catch (error) {
    console.error('Error deleting section:', error);
    alert('Failed to delete section');
  }
}

// ==================== WORD MANAGEMENT ====================

async function saveWord() {
  const hanzi = document.getElementById('wordHanzi').value.trim();
  const meaning = document.getElementById('wordMeaning').value.trim();

  if (!hanzi || !meaning) {
    alert('Please fill in all fields');
    return;
  }

  if (!currentListId || !currentSectionName) {
    alert('No list or section selected');
    return;
  }

  // Save values before closing modal (which sets them to null)
  const listId = currentListId;
  const word = { hanzi, meaning };

  try {
    let response;

    if (wordModalMode === 'edit' && editingWord) {
      // Update existing word
      response = await authFetch(`/api/vocabulary-lists/${listId}/words`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          section_name: currentSectionName,
          old_hanzi: editingWord.hanzi,
          word: word
        })
      });
    } else {
      // Add new word (pinyin will be auto-generated, level will be 'Custom')
      response = await authFetch(`/api/vocabulary-lists/${listId}/words`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          section_name: currentSectionName,
          hanzi: hanzi,
          meaning: meaning
        })
      });
    }

    if (response.ok) {
      closeWordModal();
      await viewVocabularyList(listId);
    } else {
      const error = await response.json();
      alert(`Error: ${error.detail || 'Failed to save word'}`);
    }
  } catch (error) {
    console.error('Error saving word:', error);
    alert('Failed to save word');
  }
}

async function deleteWord(listId, sectionName, hanzi) {
  if (!confirm(`Delete word "${hanzi}"?`)) {
    return;
  }

  try {
    const response = await authFetch(`/api/vocabulary-lists/${listId}/words`, {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        section_name: sectionName,
        hanzi: hanzi
      })
    });

    if (response.ok) {
      await viewVocabularyList(listId);
    } else {
      const error = await response.json();
      alert(`Error: ${error.detail || 'Failed to delete word'}`);
    }
  } catch (error) {
    console.error('Error deleting word:', error);
    alert('Failed to delete word');
  }
}

// Export functions to global scope
window.openCreateListModal = openCreateListModal;
window.closeCreateListModal = closeCreateListModal;
window.createNewList = createNewList;
window.renameList = renameList;

window.openAddSectionModal = openAddSectionModal;
window.closeAddSectionModal = closeAddSectionModal;
window.addNewSection = addNewSection;
window.renameSection = renameSection;
window.deleteSection = deleteSection;

window.openWordModal = openWordModal;
window.closeWordModal = closeWordModal;
window.saveWord = saveWord;
window.deleteWord = deleteWord;
