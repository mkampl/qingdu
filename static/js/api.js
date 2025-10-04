// API Service Layer

const API = {
  // Save text to database
  async saveText(title, content, analysisData) {
    const response = await fetch('/api/texts/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title, content, analysis_data: analysisData })
    });
    
    if (!response.ok) throw new Error('Failed to save text');
    return response.json();
  },
  
  // Get all saved texts
  async getTexts() {
    const response = await fetch('/api/texts');
    if (!response.ok) throw new Error('Failed to load texts');
    return response.json();
  },
  
  // Delete text
  async deleteText(id) {
    const response = await fetch(`/api/texts/${id}`, { method: 'DELETE' });
    if (!response.ok) throw new Error('Failed to delete text');
    return response.json();
  }
};

window.API = API;
