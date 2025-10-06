// Authentication State & UI Management

const AuthState = {
    user: null,
    token: null
  };
  
  // Initialize auth on page load
  async function initAuth() {
    const token = localStorage.getItem('auth_token');
    
    if (token) {
      AuthState.token = token;
      await checkAuth();
    } else {
      updateUIForGuest();
    }
  }
  
  // Check authentication status
  async function checkAuth() {
    try {
      const response = await fetch('/api/auth/me', {
        headers: {
          'Authorization': `Bearer ${AuthState.token}`
        }
      });
      
      const data = await response.json();
      
      if (data.authenticated) {
        AuthState.user = data.user;
        await updateUIForUser(data.user);  // Add await here
        
        if (data.user.must_change_password) {
          showChangePasswordModal(true);
        }
      } else {
        logout();
      }
    } catch (error) {
      console.error('Auth check failed:', error);
      logout();
    }
  }
  
  // Login
  async function login(username, password) {
    try {
      const response = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password })
      });
      
      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Login failed');
      }
      
      const data = await response.json();
      AuthState.token = data.access_token;
      AuthState.user = data.user;
      
      localStorage.setItem('auth_token', data.access_token);
      await updateUIForUser(data.user);  // Add await here
      closeLoginModal();
      
      if (data.user.must_change_password) {
        showChangePasswordModal(true);
      }
      
      return true;
    } catch (error) {
      alert(error.message);
      return false;
    }
  }
  
  // Logout
  function logout() {
    AuthState.user = null;
    AuthState.token = null;
    localStorage.removeItem('auth_token');
    updateUIForGuest();
  }
  
  // Update UI for authenticated user
  async function updateUIForUser(user) {
    const loginBtn = document.getElementById('loginBtn');
    const userMenu = document.getElementById('userMenu');
    const username = document.getElementById('username');
    
    if (loginBtn) loginBtn.style.display = 'none';
    if (userMenu) userMenu.style.display = 'flex';
    if (username) username.textContent = user.username;
    
    // Show/hide admin menu
    const adminMenuItem = document.getElementById('adminMenuItem');
    if (adminMenuItem) {
      adminMenuItem.style.display = user.is_admin ? 'block' : 'none';
    }
    
    // Enable save buttons and lists
    enableAuthFeatures();
    
    // Load data after login (now with await)
    await loadTextsFromStorage();
    await loadVocabularyLists();
  }
  
  // Update UI for guest
  function updateUIForGuest() {
    const loginBtn = document.getElementById('loginBtn');
    const userMenu = document.getElementById('userMenu');
    
    if (loginBtn) loginBtn.style.display = 'block';
    if (userMenu) userMenu.style.display = 'none';
    
    // Disable save buttons and lists
    disableAuthFeatures();
    
    // NEU: Behalte aktuelle Analyse, zeige nur Login-Hinweis in Sidebar
    const textsList = document.getElementById('textsList');
    const vocabLists = document.getElementById('vocabularyLists');
    
    if (textsList) {
      textsList.innerHTML = '<div style="padding:10px;color:#999;font-size:14px">🔒 Login to access saved texts</div>';
    }
    if (vocabLists) {
      vocabLists.innerHTML = '<div style="padding:10px;color:#999;font-size:14px">🔒 Login to access vocabulary lists</div>';
    }
    
    // NICHT die Analyse löschen - nur Save-Button disablen
  }
  
  // Enable features that require auth
  function enableAuthFeatures() {
    const saveBtn = document.getElementById('saveTextBtn');
    if (saveBtn) {
      saveBtn.disabled = false;
      saveBtn.title = 'Save text';
    }
  }
  
  // Disable features that require auth
  function disableAuthFeatures() {
    const saveBtn = document.getElementById('saveTextBtn');
    if (saveBtn) {
      saveBtn.disabled = true;
      saveBtn.title = 'Login required to save';
    }
    
    // Clear sidebar lists
    document.getElementById('textsList').innerHTML = 
      '<div style="padding:10px;color:#999;font-size:14px">🔒 Login to access saved texts</div>';
    document.getElementById('vocabularyLists').innerHTML = 
      '<div style="padding:10px;color:#999;font-size:14px">🔒 Login to access vocabulary lists</div>';
  }
  
  // Show login modal
  function showLoginModal() {
    const modal = document.getElementById('loginModal');
    if (modal) modal.style.display = 'flex';
  }
  
  // Close login modal
  function closeLoginModal() {
    const modal = document.getElementById('loginModal');
    if (modal) {
      modal.style.display = 'none';
      document.getElementById('loginUsername').value = '';
      document.getElementById('loginPassword').value = '';
    }
  }
  
  // Handle login form submit
  async function handleLogin(event) {
    event.preventDefault();
    const username = document.getElementById('loginUsername').value;
    const password = document.getElementById('loginPassword').value;
    await login(username, password);
  }
  
  // Show change password modal
  function showChangePasswordModal(required = false) {
    const modal = document.getElementById('changePasswordModal');
    const title = document.getElementById('changePasswordTitle');
    
    if (required && title) {
      title.textContent = 'Password Change Required';
    }
    
    if (modal) modal.style.display = 'flex';
  }
  
  // Close change password modal
  function closeChangePasswordModal() {
    const modal = document.getElementById('changePasswordModal');
    if (modal) {
      modal.style.display = 'none';
      document.getElementById('oldPassword').value = '';
      document.getElementById('newPassword').value = '';
      document.getElementById('confirmPassword').value = '';
    }
  }
  
  // Handle change password
  async function handleChangePassword(event) {
    event.preventDefault();
    
    const oldPassword = document.getElementById('oldPassword').value;
    const newPassword = document.getElementById('newPassword').value;
    const confirmPassword = document.getElementById('confirmPassword').value;
    
    if (newPassword !== confirmPassword) {
      alert('New passwords do not match');
      return;
    }
    
    if (newPassword.length < 8) {
      alert('Password must be at least 8 characters');
      return;
    }
    
    try {
      const response = await fetch('/api/auth/change-password', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${AuthState.token}`
        },
        body: JSON.stringify({
          old_password: oldPassword,
          new_password: newPassword
        })
      });
      
      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail);
      }
      
      alert('Password changed successfully');
      AuthState.user.must_change_password = false;
      closeChangePasswordModal();
    } catch (error) {
      alert(error.message);
    }
  }
  
  // Authenticated fetch wrapper
  async function authFetch(url, options = {}) {
    if (!AuthState.token) {
      throw new Error('Not authenticated');
    }
    
    options.headers = {
      ...options.headers,
      'Authorization': `Bearer ${AuthState.token}`
    };
    
    const response = await fetch(url, options);
    
    if (response.status === 401) {
      logout();
      throw new Error('Session expired, please login again');
    }
    
    return response;
  }
  
  // Export
  window.AuthState = AuthState;
  window.initAuth = initAuth;
  window.login = login;
  window.logout = logout;
  window.showLoginModal = showLoginModal;
  window.closeLoginModal = closeLoginModal;
  window.handleLogin = handleLogin;
  window.showChangePasswordModal = showChangePasswordModal;
  window.closeChangePasswordModal = closeChangePasswordModal;
  window.handleChangePassword = handleChangePassword;
  window.authFetch = authFetch;