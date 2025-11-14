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

    const title = document.createElement('h3');
    title.textContent = doc.title;
    item.appendChild(title);

    const statusParagraph = document.createElement('p');
    statusParagraph.textContent = 'Статус: ';
    const statusBadge = document.createElement('span');
    statusBadge.className = 'badge';
    statusBadge.textContent = doc.status;
    statusParagraph.appendChild(statusBadge);
    item.appendChild(statusParagraph);

    const updatedParagraph = document.createElement('p');
    updatedParagraph.textContent = `Обновлено: ${new Date(doc.updated_at).toLocaleString()}`;
    item.appendChild(updatedParagraph);

    const button = document.createElement('button');
    button.className = 'secondary';
    button.textContent = 'Открыть';
    button.dataset.id = doc.id;
    button.addEventListener('click', () => openDocument(doc.id));
    item.appendChild(button);

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
  container.innerHTML = '';

  const toolbar = document.createElement('div');
  toolbar.className = 'no-print';

  const backButton = document.createElement('button');
  backButton.className = 'secondary';
  backButton.textContent = '← Назад';
  backButton.addEventListener('click', () => setActiveSection('documents-view'));
  toolbar.appendChild(backButton);

  const printButton = document.createElement('button');
  printButton.className = 'secondary';
  printButton.textContent = 'Отправить на печать';
  printButton.addEventListener('click', () => window.print());
  toolbar.appendChild(printButton);

  container.appendChild(toolbar);

  const layout = document.createElement('div');
  layout.className = 'print-layout';

  const title = document.createElement('h2');
  title.textContent = doc.title;
  layout.appendChild(title);

  const statusParagraph = document.createElement('p');
  const statusLabel = document.createElement('strong');
  statusLabel.textContent = 'Статус:';
  statusParagraph.appendChild(statusLabel);
  statusParagraph.appendChild(document.createTextNode(` ${doc.status}`));
  layout.appendChild(statusParagraph);

  const updatedParagraph = document.createElement('p');
  const updatedLabel = document.createElement('strong');
  updatedLabel.textContent = 'Обновлено:';
  updatedParagraph.appendChild(updatedLabel);
  updatedParagraph.appendChild(
    document.createTextNode(` ${new Date(doc.updated_at).toLocaleString()}`)
  );
  layout.appendChild(updatedParagraph);

  const metadataWrapper = document.createElement('div');
  const metadataLabel = document.createElement('p');
  const metadataStrong = document.createElement('strong');
  metadataStrong.textContent = 'Метаданные:';
  metadataLabel.appendChild(metadataStrong);
  metadataWrapper.appendChild(metadataLabel);
  const metadataPre = document.createElement('pre');
  const metadataString =
    doc.metadata && Object.keys(doc.metadata).length
      ? JSON.stringify(doc.metadata, null, 2)
      : 'Нет метаданных';
  metadataPre.textContent = metadataString;
  metadataWrapper.appendChild(metadataPre);
  layout.appendChild(metadataWrapper);

  const textHeading = document.createElement('h3');
  textHeading.textContent = 'Извлеченный текст';
  layout.appendChild(textHeading);

  const textPre = document.createElement('pre');
  textPre.textContent = detail.text || 'Нет текста';
  layout.appendChild(textPre);

  const versionsHeading = document.createElement('h3');
  versionsHeading.textContent = 'Версии';
  layout.appendChild(versionsHeading);

  const versionsList = document.createElement('ul');
  versions.forEach((version) => {
    const item = document.createElement('li');
    const commentText = version.comment || 'без комментария';
    item.textContent = `v${version.version_number} — ${new Date(
      version.created_at
    ).toLocaleString()} — ${commentText}`;
    versionsList.appendChild(item);
  });
  layout.appendChild(versionsList);

  const approvalsHeading = document.createElement('h3');
  approvalsHeading.textContent = 'История согласования';
  layout.appendChild(approvalsHeading);

  const approvalsList = document.createElement('ul');
  approvals.forEach((approval) => {
    const item = document.createElement('li');
    const commentText = approval.comment || '';
    item.textContent = `Пользователь ${approval.user_id}: ${approval.status} (${commentText})`;
    approvalsList.appendChild(item);
  });
  layout.appendChild(approvalsList);

  const downloadContainer = document.createElement('div');
  downloadContainer.className = 'no-print';
  const downloadLink = document.createElement('a');
  downloadLink.className = 'primary';
  downloadLink.href = `/api/documents/${doc.id}/download`;
  downloadLink.textContent = 'Скачать';
  downloadContainer.appendChild(downloadLink);
  layout.appendChild(downloadContainer);

  container.appendChild(layout);
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
  list.innerHTML = '';

  const answerParagraph = document.createElement('p');
  const answerLabel = document.createElement('strong');
  answerLabel.textContent = 'Ответ:';
  answerParagraph.appendChild(answerLabel);
  answerParagraph.appendChild(document.createTextNode(` ${response.answer}`));
  list.appendChild(answerParagraph);

  response.results.forEach((entry) => {
    const card = document.createElement('div');
    card.className = 'card';
    const title = document.createElement('h4');
    title.textContent = entry.document.title;
    card.appendChild(title);

    const snippet = document.createElement('p');
    snippet.textContent = entry.snippet;
    card.appendChild(snippet);

    const button = document.createElement('button');
    button.className = 'secondary';
    button.textContent = 'Открыть';
    button.addEventListener('click', () => openDocument(entry.document.id));
    card.appendChild(button);

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
    usersList.innerHTML = '';
    users.forEach((user) => {
      const item = document.createElement('li');
      const rolesText = (user.roles || []).map((r) => r.name).join(', ');
      item.textContent = `${user.full_name} (${user.email}) — ${rolesText}`;
      usersList.appendChild(item);
    });

    const rolesList = document.getElementById('admin-roles');
    rolesList.innerHTML = '';
    roles.forEach((role) => {
      const item = document.createElement('li');
      item.textContent = role.name;
      rolesList.appendChild(item);
    });

    const departmentsList = document.getElementById('admin-departments');
    departmentsList.innerHTML = '';
    departments.forEach((dept) => {
      const item = document.createElement('li');
      item.textContent = dept.name;
      departmentsList.appendChild(item);
    });

    const logsList = document.getElementById('admin-logs');
    logsList.innerHTML = '';
    logs.forEach((log) => {
      const item = document.createElement('li');
      item.textContent = `${new Date(log.created_at).toLocaleString()} — ${log.action}`;
      logsList.appendChild(item);
    });
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
