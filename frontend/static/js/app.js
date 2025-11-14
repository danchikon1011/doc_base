const apiBase = '/api';
let authToken = null;
let currentUser = null;
let documentsCache = [];
let selectedDocument = null;

function setActiveSection(sectionId) {
  document.querySelectorAll('.view').forEach((el) => el.classList.add('hidden'));
  const section = document.getElementById(sectionId);
  if (section) {
    section.classList.remove('hidden');
  }
}

function setActiveNav(buttonId) {
  document.querySelectorAll('nav button').forEach((btn) => btn.classList.remove('active'));
  const button = document.getElementById(buttonId);
  if (button) {
    button.classList.add('active');
  }
}

async function apiRequest(path, options = {}) {
  const headers = options.headers || {};
  if (authToken) {
    headers['Authorization'] = `Bearer ${authToken}`;
  }
  if (!(options.body instanceof FormData)) {
    headers['Content-Type'] = headers['Content-Type'] || 'application/json';
  }
  const response = await fetch(`${apiBase}${path}`, {
    ...options,
    headers,
  });
  if (response.status === 401) {
    alert('Сессия истекла, пожалуйста войдите снова');
    showLogin();
    throw new Error('Unauthorized');
  }
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || 'Request failed');
  }
  const contentType = response.headers.get('content-type') || '';
  if (contentType.includes('application/json')) {
    return response.json();
  }
  return response;
}

function showLogin() {
  setActiveSection('login-view');
  setActiveNav('nav-login');
}

async function handleLogin(event) {
  event.preventDefault();
  const form = event.target;
  const data = new FormData();
  data.append('username', form.email.value);
  data.append('password', form.password.value);

  try {
    const result = await apiRequest('/auth/login', { method: 'POST', body: data });
    authToken = result.access_token;
    localStorage.setItem('token', authToken);
    await loadDocuments();
    setActiveNav('nav-documents');
    setActiveSection('documents-view');
  } catch (error) {
    alert('Ошибка входа: ' + error.message);
  }
}

async function loadDocuments() {
  try {
    const docs = await apiRequest('/documents/');
    documentsCache = docs;
    renderDocuments(docs);
  } catch (error) {
    console.error('Failed to load documents', error);
  }
}

function renderDocuments(documents) {
  const list = document.getElementById('documents-list');
  list.innerHTML = '';
  documents.forEach((doc) => {
    const item = document.createElement('div');
    item.className = 'card';
    item.innerHTML = `
      <h3>${doc.title}</h3>
      <p>Статус: <span class="badge">${doc.status}</span></p>
      <p>Обновлено: ${new Date(doc.updated_at).toLocaleString()}</p>
      <button class="secondary" data-id="${doc.id}">Открыть</button>
    `;
    item.querySelector('button').addEventListener('click', () => openDocument(doc.id));
    list.appendChild(item);
  });
}

async function openDocument(id) {
  try {
    const result = await apiRequest(`/documents/${id}`);
    selectedDocument = result;
    renderDocumentDetail(result);
    setActiveNav('nav-documents');
    setActiveSection('document-detail-view');
  } catch (error) {
    alert('Не удалось открыть документ: ' + error.message);
  }
}

function renderDocumentDetail(detail) {
  const container = document.getElementById('document-detail');
  const doc = detail.document;
  const versions = detail.versions || [];
  const approvals = detail.approvals || [];
  container.innerHTML = `
    <div class="no-print">
      <button class="secondary" onclick="setActiveSection('documents-view')">← Назад</button>
      <button class="secondary" onclick="window.print()">Отправить на печать</button>
    </div>
    <div class="print-layout">
      <h2>${doc.title}</h2>
      <p><strong>Статус:</strong> ${doc.status}</p>
      <p><strong>Обновлено:</strong> ${new Date(doc.updated_at).toLocaleString()}</p>
      <p><strong>Метаданные:</strong> <pre>${JSON.stringify(doc.metadata, null, 2)}</pre></p>
      <h3>Извлеченный текст</h3>
      <pre>${detail.text || 'Нет текста'}</pre>
      <h3>Версии</h3>
      <ul>
        ${versions
          .map(
            (version) => `<li>v${version.version_number} — ${new Date(version.created_at).toLocaleString()} — ${
              version.comment || 'без комментария'
            }</li>`
          )
          .join('')}
      </ul>
      <h3>История согласования</h3>
      <ul>
        ${approvals
          .map(
            (approval) => `<li>Пользователь ${approval.user_id}: ${approval.status} (${approval.comment || ''})</li>`
          )
          .join('')}
      </ul>
      <div class="no-print">
        <a class="primary" href="/api/documents/${doc.id}/download">Скачать</a>
      </div>
    </div>
  `;
}

async function handleDocumentSearch(event) {
  event.preventDefault();
  const query = event.target.search.value;
  const results = await apiRequest(`/documents/search?q=${encodeURIComponent(query)}`);
  renderDocuments(results.map((item) => item.document));
}

async function handleSmartSearch(event) {
  event.preventDefault();
  const question = event.target.question.value;
  const response = await apiRequest(`/documents/smart-search?question=${encodeURIComponent(question)}`);
  const list = document.getElementById('smart-search-results');
  list.innerHTML = `<p><strong>Ответ:</strong> ${response.answer}</p>`;
  response.results.forEach((entry) => {
    const card = document.createElement('div');
    card.className = 'card';
    card.innerHTML = `
      <h4>${entry.document.title}</h4>
      <p>${entry.snippet}</p>
      <button class="secondary">Открыть</button>
    `;
    card.querySelector('button').addEventListener('click', () => openDocument(entry.document.id));
    list.appendChild(card);
  });
}

async function handleUpload(event) {
  event.preventDefault();
  const form = event.target;
  const data = new FormData(form);
  const sharedUsers = form.shared_user_ids.value
    .split(',')
    .map((v) => v.trim())
    .filter(Boolean)
    .map((v) => Number(v));
  const reviewers = form.reviewers.value
    .split(',')
    .map((v) => v.trim())
    .filter(Boolean)
    .map((v) => Number(v));
  data.set('shared_user_ids', JSON.stringify(sharedUsers));
  data.set('reviewers', JSON.stringify(reviewers));

  try {
    await apiRequest('/documents/upload', { method: 'POST', body: data });
    alert('Документ загружен');
    form.reset();
    await loadDocuments();
    setActiveSection('documents-view');
  } catch (error) {
    alert('Не удалось загрузить документ: ' + error.message);
  }
}

async function loadAdminData() {
  try {
    const [users, roles, departments, logs] = await Promise.all([
      apiRequest('/admin/users'),
      apiRequest('/admin/roles'),
      apiRequest('/admin/departments'),
      apiRequest('/admin/audit-logs'),
    ]);
    const usersList = document.getElementById('admin-users');
    usersList.innerHTML = users
      .map((user) => `<li>${user.full_name} (${user.email}) — ${user.roles.map((r) => r.name).join(', ')}</li>`)
      .join('');
    document.getElementById('admin-roles').innerHTML = roles.map((role) => `<li>${role.name}</li>`).join('');
    document.getElementById('admin-departments').innerHTML = departments
      .map((dept) => `<li>${dept.name}</li>`)
      .join('');
    document.getElementById('admin-logs').innerHTML = logs
      .map((log) => `<li>${new Date(log.created_at).toLocaleString()} — ${log.action}</li>`)
      .join('');
  } catch (error) {
    console.error('Failed to load admin data', error);
  }
}

function init() {
  document.getElementById('login-form').addEventListener('submit', handleLogin);
  document.getElementById('search-form').addEventListener('submit', handleDocumentSearch);
  document.getElementById('smart-search-form').addEventListener('submit', handleSmartSearch);
  document.getElementById('upload-form').addEventListener('submit', handleUpload);

  document.getElementById('nav-login').addEventListener('click', () => {
    setActiveNav('nav-login');
    showLogin();
  });
  document.getElementById('nav-documents').addEventListener('click', async () => {
    setActiveNav('nav-documents');
    setActiveSection('documents-view');
    await loadDocuments();
  });
  document.getElementById('nav-upload').addEventListener('click', () => {
    setActiveNav('nav-upload');
    setActiveSection('upload-view');
  });
  document.getElementById('nav-smart-search').addEventListener('click', () => {
    setActiveNav('nav-smart-search');
    setActiveSection('smart-search-view');
  });
  document.getElementById('nav-admin').addEventListener('click', async () => {
    setActiveNav('nav-admin');
    setActiveSection('admin-view');
    await loadAdminData();
  });

  const storedToken = localStorage.getItem('token');
  if (storedToken) {
    authToken = storedToken;
    setActiveNav('nav-documents');
    setActiveSection('documents-view');
    loadDocuments();
  } else {
    showLogin();
  }
}

window.addEventListener('DOMContentLoaded', init);
