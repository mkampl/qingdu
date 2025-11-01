# QingDu API Documentation

Complete API reference for QingDu Chinese Text Analyzer.

## Table of Contents

- [Authentication](#authentication)
- [Analysis Endpoints](#analysis-endpoints)
- [Text Management](#text-management)
- [Vocabulary Management](#vocabulary-management)
- [User Management](#user-management)
- [Admin Endpoints](#admin-endpoints)
- [Invitation System](#invitation-system)
- [Rate Limiting](#rate-limiting)

---

## Authentication

Most endpoints require JWT authentication. Include the token in the `Authorization` header:

```
Authorization: Bearer <your_jwt_token>
```

### Login
```http
POST /api/auth/login
```

**Request Body:**
```json
{
  "username": "admin",
  "password": "admin123"
}
```

**Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "user": {
    "username": "admin",
    "is_admin": true,
    "must_change_password": false
  }
}
```

### Get Current User
```http
GET /api/auth/me
```

**Headers:** `Authorization: Bearer <token>`

**Response:**
```json
{
  "authenticated": true,
  "user": {
    "username": "admin",
    "is_admin": true,
    "must_change_password": false
  }
}
```

### Change Password
```http
POST /api/auth/change-password
```

**Headers:** `Authorization: Bearer <token>`

**Request Body:**
```json
{
  "old_password": "oldpass",
  "new_password": "newpass123"
}
```

---

## Analysis Endpoints

### Analyze Text
```http
POST /api/analyze
```

**Rate Limit:** 30 requests/minute

**Request Body:**
```json
{
  "text": "我今天去学校学习中文。"
}
```

**Response:**
```json
{
  "words": [
    {
      "text": "我",
      "is_hsk": true,
      "hsk_level": "HSK 1",
      "pinyin": "wǒ",
      "meaning": "I, me",
      "meanings": ["I", "me"],
      "frequency": 9,
      "translation_source": "local"
    },
    ...
  ],
  "estimated_level": "HSK 2",
  "hsk_stats": {
    "hsk1": 5,
    "hsk2": 3,
    "hsk3": 1,
    ...
  }
}
```

### Translate Text
```http
POST /api/translate
```

**Rate Limit:** 20 requests/minute

**Request Body:**
```json
{
  "text": "我今天去学校学习中文。",
  "source_lang": "zh",
  "target_lang": "en"
}
```

**Response:**
```json
{
  "translation": "I went to school to study Chinese today.",
  "source": "deepl"
}
```

Translation priority: DeepL → Google Translate → MyMemory (free)

### Text-to-Speech
```http
GET /api/tts/{text}
```

**Parameters:**
- `text` (path) - Chinese text to convert to speech
- `lang` (query, optional) - Language code (default: "zh-cn")

**Response:** Audio file (mp3)

**Example:**
```http
GET /api/tts/你好?lang=zh-cn
```

---

## Text Management

### Get All Saved Texts
```http
GET /api/texts
```

**Headers:** `Authorization: Bearer <token>`

**Response:**
```json
[
  {
    "id": 1,
    "title": "First Lesson",
    "text": "我今天去学校...",
    "analysis_data": {...},
    "created_at": "2025-11-01T10:30:00",
    "tags": ["lesson", "beginner"]
  },
  ...
]
```

### Save Text
```http
POST /api/texts/save
```

**Headers:** `Authorization: Bearer <token>`

**Request Body:**
```json
{
  "title": "My First Text",
  "text": "我今天去学校学习中文。",
  "analysis_data": {...},
  "tags": ["lesson", "hsk2"]
}
```

**Response:**
```json
{
  "id": 1,
  "title": "My First Text",
  "created_at": "2025-11-01T10:30:00"
}
```

### Update Text
```http
PATCH /api/texts/{text_id}
```

**Headers:** `Authorization: Bearer <token>`

**Request Body:**
```json
{
  "title": "Updated Title",
  "text": "Updated Chinese text...",
  "tags": ["updated", "hsk3"]
}
```

### Delete Text
```http
DELETE /api/texts/{text_id}
```

**Headers:** `Authorization: Bearer <token>`

**Response:** `204 No Content`

### Update Reading Progress
```http
PATCH /api/texts/{text_id}/progress
```

**Headers:** `Authorization: Bearer <token>`

**Request Body:**
```json
{
  "reading_progress": 75
}
```

---

## Vocabulary Management

### Get Vocabulary Statistics
```http
GET /api/vocabulary-stats
```

**Response:**
```json
{
  "loaded": true,
  "count": 11247
}
```

### Get Complete HSK Vocabulary
```http
GET /api/get-hsk-vocabulary
```

**Response:**
```json
{
  "你好": {
    "level": "HSK 1",
    "pinyin": "nǐ hǎo",
    "meaning": "hello",
    "meanings": ["hello", "hi"]
  },
  ...
}
```

### Get Vocabulary Lists
```http
GET /api/vocabulary/lists
```

**Headers:** `Authorization: Bearer <token>`

**Response:**
```json
[
  {
    "id": 1,
    "name": "HSK 2 Study List",
    "description": "Words from HSK 2",
    "created_at": "2025-11-01T10:00:00",
    "word_count": 25
  },
  ...
]
```

### Create Vocabulary List
```http
POST /api/vocabulary/lists
```

**Headers:** `Authorization: Bearer <token>`

**Request Body:**
```json
{
  "name": "My HSK 3 List",
  "description": "Important HSK 3 words"
}
```

### Add Word to List
```http
POST /api/vocabulary/lists/{list_id}/words
```

**Headers:** `Authorization: Bearer <token>`

**Request Body:**
```json
{
  "word": "学习",
  "pinyin": "xué xí",
  "meaning": "to study",
  "hsk_level": "HSK 2"
}
```

### Delete Vocabulary List
```http
DELETE /api/vocabulary/lists/{list_id}
```

**Headers:** `Authorization: Bearer <token>`

---

## User Management

### Signup with Invitation
```http
POST /api/auth/signup-with-invite
```

**Request Body:**
```json
{
  "token": "630268cb-270d-4cb8-a1d8-34aee2c5c7c6",
  "username": "newuser",
  "password": "securepass123"
}
```

**Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "user": {
    "username": "newuser",
    "is_admin": false
  }
}
```

---

## Admin Endpoints

All admin endpoints require authentication with admin privileges.

### Get All Users
```http
GET /api/admin/users
```

**Headers:** `Authorization: Bearer <admin_token>`

**Response:**
```json
[
  {
    "id": 1,
    "username": "admin",
    "is_admin": true,
    "invite_quota": 5,
    "created_at": "2025-01-01T00:00:00",
    "last_active": "2025-11-01T10:00:00"
  },
  ...
]
```

### Create User
```http
POST /api/admin/users
```

**Headers:** `Authorization: Bearer <admin_token>`

**Request Body:**
```json
{
  "username": "newuser",
  "password": "temppass123"
}
```

### Reset User Password
```http
POST /api/admin/users/{user_id}/reset-password
```

**Headers:** `Authorization: Bearer <admin_token>`

**Request Body:**
```json
{
  "new_password": "newtemp123"
}
```

**Note:** User will be required to change password on next login.

### Toggle Admin Status
```http
POST /api/admin/users/{user_id}/toggle-admin
```

**Headers:** `Authorization: Bearer <admin_token>`

### Update User Invite Quota
```http
PATCH /api/admin/users/{user_id}/invite-quota
```

**Headers:** `Authorization: Bearer <admin_token>`

**Request Body:**
```json
{
  "invite_quota": 10
}
```

### Delete User
```http
DELETE /api/admin/users/{user_id}
```

**Headers:** `Authorization: Bearer <admin_token>`

**Response:** `204 No Content`

**Note:** This deletes all user data including texts and vocabulary lists.

---

## Invitation System

### Validate Invitation Token
```http
GET /api/invitations/validate/{token}
```

**Response:**
```json
{
  "valid": true,
  "invited_by": "admin",
  "expires_at": "2025-12-01T00:00:00"
}
```

**Error Response:**
```json
{
  "valid": false,
  "reason": "already_used"
}
```

Possible reasons: `"not_found"`, `"already_used"`, `"expired"`

### Get My Invitations
```http
GET /api/invitations/my-invitations
```

**Headers:** `Authorization: Bearer <token>`

**Response:**
```json
{
  "remaining_quota": 3,
  "invitations": [
    {
      "token": "630268cb-270d-4cb8-a1d8-34aee2c5c7c6",
      "invite_url": "http://localhost:8000/?invite=630268cb-...",
      "claimed": false,
      "claimed_by": null,
      "created_at": "2025-11-01T10:00:00",
      "expires_at": "2025-12-01T10:00:00"
    },
    ...
  ]
}
```

### Generate Invitation
```http
POST /api/invitations/generate
```

**Headers:** `Authorization: Bearer <token>`

**Response:**
```json
{
  "token": "630268cb-270d-4cb8-a1d8-34aee2c5c7c6",
  "invite_url": "http://localhost:8000/?invite=630268cb-270d-4cb8-a1d8-34aee2c5c7c6",
  "expires_at": "2025-12-01T10:00:00"
}
```

**Error Response (no quota):**
```json
{
  "detail": "No invitation quota remaining"
}
```

---

## Rate Limiting

API endpoints have rate limits to prevent abuse:

- **Analysis:** 30 requests/minute
- **Translation:** 20 requests/minute
- **Authentication:** 5 requests/minute

**Rate Limit Headers:**
```
X-RateLimit-Limit: 30
X-RateLimit-Remaining: 25
X-RateLimit-Reset: 1635782400
```

**Rate Limit Exceeded Response:**
```http
HTTP/1.1 429 Too Many Requests
Content-Type: application/json

{
  "detail": "Rate limit exceeded. Please try again later."
}
```

---

## Error Responses

All endpoints return standardized error responses:

**400 Bad Request:**
```json
{
  "detail": "Invalid request parameters"
}
```

**401 Unauthorized:**
```json
{
  "detail": "Not authenticated"
}
```

**403 Forbidden:**
```json
{
  "detail": "Not enough permissions"
}
```

**404 Not Found:**
```json
{
  "detail": "Resource not found"
}
```

**500 Internal Server Error:**
```json
{
  "detail": "Internal server error"
}
```

---

## Interactive API Documentation

QingDu includes auto-generated interactive API documentation powered by FastAPI:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

These provide a complete, interactive interface to test all API endpoints.

---

_For questions or issues, please [open an issue](https://github.com/mkampl/qingdu/issues) on GitHub._
