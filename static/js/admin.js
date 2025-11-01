// Admin Panel JavaScript

let currentResetUserId = null;

// Initialize on page load
// Initialize on page load
window.onload = async function() {
    // Load token from localStorage
    const token = localStorage.getItem('auth_token');
    
    if (!token) {
      alert('Not authenticated. Please login first.');
      window.location.href = '/';
      return;
    }
    
    // Set auth state
    AuthState.token = token;
    
    // Verify authentication and check admin status
    try {
      const response = await fetch('/api/auth/me', {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      
      const data = await response.json();
      
      if (!data.authenticated) {
        alert('Session expired. Please login again.');
        localStorage.removeItem('auth_token');
        window.location.href = '/';
        return;
      }
      
      if (!data.user.is_admin) {
        alert('Access denied. Admin only.');
        window.location.href = '/';
        return;
      }
      
      AuthState.user = data.user;
      await loadUsers();
      
    } catch (error) {
      console.error('Auth check failed:', error);
      alert('Authentication error. Please login again.');
      window.location.href = '/';
    }
  };

// Load all users
async function loadUsers() {
  try {
    const response = await authFetch('/api/admin/users');
    
    if (!response.ok) {
      throw new Error('Failed to load users');
    }
    
    const users = await response.json();
    displayUsers(users);
  } catch (error) {
    alert('Failed to load users: ' + error.message);
    document.getElementById('userTableBody').innerHTML = 
      '<tr><td colspan="5" style="color: #dc3545;">Error loading users</td></tr>';
  }
}
async function toggleAdmin(userId, username, isCurrentlyAdmin) {
    const action = isCurrentlyAdmin ? 'remove admin rights from' : 'make admin';
    if (!confirm(`${action} '${username}'?`)) return;
    
    try {
      const response = await authFetch(`/api/admin/users/${userId}/toggle-admin`, {
        method: 'POST'
      });
      
      if (!response.ok) throw new Error('Failed to toggle admin status');
      
      await loadUsers();
    } catch (error) {
      alert('Failed: ' + error.message);
    }
  }

// Display users in table
function displayUsers(users) {
  const tbody = document.getElementById('userTableBody');

  if (users.length === 0) {
    tbody.innerHTML = '<tr><td colspan="6" style="text-align: center;">No users found</td></tr>';
    return;
  }

  tbody.innerHTML = users.map(user => {
    const createdDate = new Date(user.created_at).toLocaleDateString();
    const lastActive = new Date(user.last_active).toLocaleDateString();
    const inviteQuota = user.invite_quota !== undefined ? user.invite_quota : 5;
    const quotaDisplay = inviteQuota === -1 ? 'Unlimited' : inviteQuota;

    return `
      <tr>
        <td>${user.username}</td>
        <td>${user.is_admin ? '✅ Admin' : '👤 User'}</td>
        <td>
          <span id="quota-${user.id}" style="cursor: pointer; padding: 4px 8px; background: #f0f0f0; border-radius: 4px;"
                onclick="editQuota(${user.id}, ${inviteQuota})"
                title="Click to edit">
            ${quotaDisplay}
          </span>
        </td>
        <td>${createdDate}</td>
        <td>${lastActive}</td>
        <td>
          <button class="action-btn btn-warning" onclick="showResetPasswordModal(${user.id}, '${user.username}')">
            🔑 Reset Password
          </button>
          ${!user.is_admin ? `
            <button class="action-btn btn-danger" onclick="deleteUser(${user.id}, '${user.username}')">
              🗑️ Delete
            </button>
          ` : ''}
          <button class="action-btn" style="background: #17a2b8; color: white;"
                    onclick="toggleAdmin(${user.id}, '${user.username}', ${user.is_admin})">
            ${user.is_admin ? '⬇️ Remove Admin' : '⬆️ Make Admin'}
            </button>
        </td>
      </tr>
    `;
  }).join('');
}

// Edit quota inline
function editQuota(userId, currentQuota) {
  const span = document.getElementById(`quota-${userId}`);
  const input = document.createElement('input');
  input.type = 'number';
  input.value = currentQuota;
  input.min = '-1';
  input.style.width = '60px';
  input.style.padding = '4px';
  input.style.border = '2px solid #667eea';
  input.style.borderRadius = '4px';

  span.replaceWith(input);
  input.focus();
  input.select();

  const saveQuota = async () => {
    const newQuota = parseInt(input.value);

    if (isNaN(newQuota) || newQuota < -1) {
      alert('Invalid quota value');
      await loadUsers();
      return;
    }

    try {
      const response = await authFetch(`/api/admin/users/${userId}/invite-quota`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ invite_quota: newQuota })
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to update quota');
      }

      await loadUsers();
    } catch (error) {
      alert('Failed to update quota: ' + error.message);
      await loadUsers();
    }
  };

  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();  // Prevent blur event from firing
      saveQuota();
    }
    if (e.key === 'Escape') loadUsers();
  });

  input.addEventListener('blur', saveQuota);
}

// Show create user modal
function showCreateUserModal() {
  document.getElementById('createUserModal').style.display = 'flex';
  document.getElementById('newUsername').value = '';
  document.getElementById('newPassword').value = '';
}

// Close create user modal
function closeCreateUserModal() {
  document.getElementById('createUserModal').style.display = 'none';
}

// Handle create user form
async function handleCreateUser(event) {
  event.preventDefault();
  
  const username = document.getElementById('newUsername').value;
  const password = document.getElementById('newPassword').value;
  
  if (password.length < 8) {
    alert('Password must be at least 8 characters');
    return;
  }
  
  try {
    const response = await authFetch('/api/admin/users', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password })
    });
    
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to create user');
    }
    
    alert(`User '${username}' created successfully!`);
    closeCreateUserModal();
    await loadUsers();
  } catch (error) {
    alert('Failed to create user: ' + error.message);
  }
}

// Show reset password modal
function showResetPasswordModal(userId, username) {
  currentResetUserId = userId;
  document.getElementById('resetUserId').value = userId;
  document.getElementById('resetUsername').textContent = username;
  document.getElementById('resetPasswordModal').style.display = 'flex';
  document.getElementById('resetNewPassword').value = '';
}

// Close reset password modal
function closeResetPasswordModal() {
  document.getElementById('resetPasswordModal').style.display = 'none';
  currentResetUserId = null;
}

// Handle reset password form
async function handleResetPassword(event) {
  event.preventDefault();
  
  const userId = currentResetUserId;
  const newPassword = document.getElementById('resetNewPassword').value;
  
  if (newPassword.length < 8) {
    alert('Password must be at least 8 characters');
    return;
  }
  
  try {
    const response = await authFetch(`/api/admin/users/${userId}/reset-password`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ new_password: newPassword })
    });
    
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to reset password');
    }
    
    alert('Password reset successfully! User will be required to change it on next login.');
    closeResetPasswordModal();
  } catch (error) {
    alert('Failed to reset password: ' + error.message);
  }
}

// Delete user
async function deleteUser(userId, username) {
  if (!confirm(`Delete user '${username}'? This cannot be undone and will delete all their texts and vocabulary lists.`)) {
    return;
  }
  
  try {
    const response = await authFetch(`/api/admin/users/${userId}`, {
      method: 'DELETE'
    });
    
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to delete user');
    }
    
    alert(`User '${username}' deleted successfully`);
    await loadUsers();
  } catch (error) {
    alert('Failed to delete user: ' + error.message);
  }
}

// Export functions
window.showCreateUserModal = showCreateUserModal;
window.closeCreateUserModal = closeCreateUserModal;
window.handleCreateUser = handleCreateUser;
window.showResetPasswordModal = showResetPasswordModal;
window.closeResetPasswordModal = closeResetPasswordModal;
window.handleResetPassword = handleResetPassword;
window.deleteUser = deleteUser;
window.editQuota = editQuota;
window.toggleAdmin = toggleAdmin;