# Users API Frontend Integration

This project already exposes user APIs under:

- `http://127.0.0.1:8000/api/auth/login/`
- `http://127.0.0.1:8000/api/auth/logout/`
- `http://127.0.0.1:8000/api/users/`
- `http://127.0.0.1:8000/api/users/profile/`
- `http://127.0.0.1:8000/api/users/staff/`
- `http://127.0.0.1:8000/api/users/{id}/change_password/`

Use the client in `frontend-integration/users-api-client.js` in your frontend app.

## 1) Copy the client into your frontend

Copy `users-api-client.js` into your frontend source folder, then import it.

## 2) Basic usage

```javascript
import { createUsersApi } from "./users-api-client";

const api = createUsersApi({
  baseUrl: "http://127.0.0.1:8000/api",
  inactivityTimeoutMs: 5 * 60 * 1000,
  onSessionExpired: () => {
    // Redirect to login route when user is auto-logged-out.
    window.location.href = "/login";
  },
});

async function loginAndLoadUsers() {
  await api.login({
    email: "admin@example.com",
    password: "StrongPass123!",
  });

  const me = await api.getProfile();
  const usersPage = await api.listUsers({ page: 1, search: "john" });

  console.log("Logged in user", me);
  console.log("Users", usersPage);
}
```

## 3) Logout logic

```javascript
// Manual logout from logout button/menu.
await api.logout();

// Optional route redirect after logout.
window.location.href = "/login";
```

## 4) Create user from frontend

```javascript
await api.createUser({
  username: "doctor1",
  email: "doctor1@example.com",
  first_name: "Jane",
  last_name: "Doe",
  role: "doctor",
  phone: "0708320123",
  department: "Cardiology",
  is_active: true,
  is_verified: true,
});
```

## 5) Change password

```javascript
await api.changePassword(7, {
  old_password: "OldPass123!",
  new_password: "NewStrongPass123!",
  confirm_password: "NewStrongPass123!",
});
```

## 5) Error handling pattern

```javascript
try {
  await api.createUser(payload);
} catch (error) {
  console.error("HTTP status", error.status);
  console.error("API error payload", error.data);
}
```

## Notes

- Auth uses JWT bearer token from `/api/auth/login/`.
- Logout endpoint is `/api/auth/logout/`.
- The client stores access/refresh tokens in `localStorage`.
- Session inactivity auto-logout is enabled by default and set to 5 minutes.
- Any user activity resets the inactivity timer.
- CORS is already configured in Django settings for `localhost:3000` and `localhost:4200`.
- For production, set `baseUrl` to your API domain.
