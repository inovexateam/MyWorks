# Agent: WebForms → React 18 + TypeScript

## Identity
Converts .aspx pages to React 18 functional components with TypeScript.
Works from AST JSON — never re-reads .aspx files directly.
Generates: React component, API controller, TypeScript types, routes.

## Pre-work
1. Check CODEBASE-MAP.md hash — skip ✅ DONE
2. Read .github/memory/ast/[PageName].json (MUST exist — run agent-roslyn-ast first)
3. Never load the .aspx file directly if AST exists

## What gets generated per screen

### File structure
```
src-core/WebApp.Core/ClientApp/src/
├── pages/
│   └── [PageName]/
│       ├── [PageName].tsx          ← main component
│       ├── [PageName].types.ts     ← TypeScript interfaces
│       ├── [PageName].hooks.ts     ← data fetching hooks
│       └── [PageName].test.tsx     ← basic tests
└── components/
    └── shared/                     ← reusable components

src-core/WebApp.Core/
└── Presentation/Controllers/
    └── [PageName]ApiController.cs  ← API endpoints from ast.apiEndpoints[]
```

---

## Generation rules from AST

### TypeScript types (from ast.dataBindings[])
```typescript
// [PageName].types.ts
export interface Customer {
  id: number;
  name: string;
  email: string;
  status: string;
}

export interface CustomerListParams {
  search?: string;
  status?: string;
  page?: number;
  pageSize?: number;
}

export interface PagedResult<T> {
  items: T[];
  totalCount: number;
  page: number;
  pageSize: number;
}
```

### Data hook (from ast.dataBindings[] + ast.apiEndpoints[])
```typescript
// [PageName].hooks.ts
import { useState, useEffect, useCallback } from 'react';
import type { Customer, CustomerListParams, PagedResult } from './CustomerList.types';

export function useCustomers(params: CustomerListParams) {
  const [data, setData] = useState<PagedResult<Customer> | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetch = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const qs = new URLSearchParams(params as Record<string, string>).toString();
      const resp = await window.fetch(`/api/customers?${qs}`, {
        headers: { 'RequestVerificationToken': getAntiForgeryToken() }
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      setData(await resp.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  }, [JSON.stringify(params)]);

  useEffect(() => { fetch(); }, [fetch]);

  return { data, loading, error, refetch: fetch };
}

function getAntiForgeryToken(): string {
  return document.querySelector<HTMLMetaElement>('meta[name="csrf-token"]')?.content ?? '';
}
```

### Main component (from ast.controls[] + ast.events[])

#### GridView + Search + UpdatePanel pattern
```tsx
// CustomerList.tsx
import React, { useState } from 'react';
import type { Customer, CustomerListParams } from './CustomerList.types';
import { useCustomers } from './CustomerList.hooks';

export default function CustomerList() {
  const [params, setParams] = useState<CustomerListParams>({ page: 1, pageSize: 20 });

  const { data, loading, error, refetch } = useCustomers(params);

  // Maps: btnSearch_Click → handleSearch
  const handleSearch = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    setParams(p => ({ ...p, search: fd.get('search') as string, page: 1 }));
  };

  // Maps: gvCustomers_RowCommand "Delete" → handleDelete
  const handleDelete = async (id: number) => {
    if (!confirm('Delete this customer?')) return;
    await window.fetch(`/api/customers/${id}`, {
      method: 'DELETE',
      headers: { 'RequestVerificationToken': getAntiForgeryToken() }
    });
    refetch();
  };

  // Maps: btnAdd_Click → navigate to Add page
  const handleAdd = () => { window.location.href = '/customers/add'; };

  if (error) return <div className="alert alert-danger">{error}</div>;

  return (
    <div className="container-fluid">
      {/* Maps: MasterPage → Layout wrapper (handled by router) */}
      <h2>Customer List</h2>

      {/* Maps: TextBox txtSearch + Button btnSearch */}
      <form onSubmit={handleSearch} className="row g-2 mb-3">
        <div className="col-auto">
          <input name="search" type="text" className="form-control"
            placeholder="Search..." defaultValue={params.search} />
        </div>
        <div className="col-auto">
          <button type="submit" className="btn btn-primary">Search</button>
        </div>
        <div className="col-auto">
          <button type="button" onClick={handleAdd} className="btn btn-success">Add New</button>
        </div>
      </form>

      {/* Maps: GridView gvCustomers with paging */}
      {loading ? (
        <div className="text-center"><div className="spinner-border" /></div>
      ) : (
        <>
          <table className="table table-striped table-hover">
            <thead>
              <tr>
                <th>Name</th><th>Email</th><th>Status</th><th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {data?.items.map(c => (
                <tr key={c.id}>
                  <td>{c.name}</td>
                  <td>{c.email}</td>
                  <td><span className={`badge bg-${c.status === 'Active' ? 'success' : 'secondary'}`}>{c.status}</span></td>
                  <td>
                    <a href={`/customers/edit/${c.id}`} className="btn btn-sm btn-outline-primary me-1">Edit</a>
                    <button onClick={() => handleDelete(c.id)} className="btn btn-sm btn-outline-danger">Delete</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {/* Pagination — replaces GridView AllowPaging */}
          {data && data.totalCount > data.pageSize && (
            <nav>
              <ul className="pagination">
                {Array.from({ length: Math.ceil(data.totalCount / data.pageSize) }, (_, i) => (
                  <li key={i} className={`page-item ${data.page === i + 1 ? 'active' : ''}`}>
                    <button className="page-link" onClick={() => setParams(p => ({ ...p, page: i + 1 }))}>{i + 1}</button>
                  </li>
                ))}
              </ul>
            </nav>
          )}
        </>
      )}
    </div>
  );
}
```

#### Form / Entry page pattern (simple CRUD)
```tsx
// CustomerEdit.tsx
import React, { useState, useEffect } from 'react';

interface Props { id?: number; }

export default function CustomerEdit({ id }: Props) {
  const [form, setForm] = useState({ name: '', email: '', status: 'Active' });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const isEdit = Boolean(id);

  useEffect(() => {
    if (!id) return;
    window.fetch(`/api/customers/${id}`)
      .then(r => r.json())
      .then(setForm);
  }, [id]);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm(f => ({ ...f, [e.target.name]: e.target.value }));

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    const resp = await window.fetch(
      isEdit ? `/api/customers/${id}` : '/api/customers',
      {
        method: isEdit ? 'PUT' : 'POST',
        headers: {
          'Content-Type': 'application/json',
          'RequestVerificationToken': getAntiForgeryToken()
        },
        body: JSON.stringify(form)
      }
    );
    if (resp.ok) {
      window.location.href = '/customers';
    } else {
      const errs = await resp.json();
      setErrors(errs.errors ?? {});
    }
    setSaving(false);
  };

  return (
    <form onSubmit={handleSubmit} className="row g-3">
      <h2>{isEdit ? 'Edit' : 'Add'} Customer</h2>

      <div className="col-md-6">
        <label className="form-label">Name</label>
        <input name="name" value={form.name} onChange={handleChange}
          className={`form-control ${errors.name ? 'is-invalid' : ''}`} required maxLength={200} />
        {errors.name && <div className="invalid-feedback">{errors.name}</div>}
      </div>

      <div className="col-md-6">
        <label className="form-label">Email</label>
        <input name="email" type="email" value={form.email} onChange={handleChange}
          className={`form-control ${errors.email ? 'is-invalid' : ''}`} required />
        {errors.email && <div className="invalid-feedback">{errors.email}</div>}
      </div>

      <div className="col-md-4">
        <label className="form-label">Status</label>
        <select name="status" value={form.status} onChange={handleChange} className="form-select">
          <option>Active</option>
          <option>Inactive</option>
        </select>
      </div>

      <div className="col-12">
        <button type="submit" className="btn btn-primary me-2" disabled={saving}>
          {saving ? 'Saving...' : 'Save'}
        </button>
        <a href="/customers" className="btn btn-secondary">Cancel</a>
      </div>
    </form>
  );
}
```

### API Controller (from ast.apiEndpoints[])
```csharp
// Presentation/Controllers/CustomersApiController.cs
[ApiController]
[Route("api/[controller]")]
[Authorize]
public class CustomersController(ICustomerService service) : ControllerBase
{
    [HttpGet]
    public async Task<ActionResult<PagedResult<CustomerDto>>> GetAll(
        [FromQuery] string? search, [FromQuery] string? status,
        [FromQuery] int page = 1, [FromQuery] int pageSize = 20,
        CancellationToken ct = default)
        => Ok(await service.GetPagedAsync(search, status, page, pageSize, ct));

    [HttpGet("{id:int}")]
    public async Task<ActionResult<CustomerDto>> GetById(int id, CancellationToken ct)
        => await service.GetByIdAsync(id, ct) is { } c ? Ok(c) : NotFound();

    [HttpPost]
    public async Task<ActionResult<CustomerDto>> Create(
        CreateCustomerDto dto, CancellationToken ct)
    {
        var created = await service.CreateAsync(dto, ct);
        return CreatedAtAction(nameof(GetById), new { id = created.Id }, created);
    }

    [HttpPut("{id:int}")]
    public async Task<ActionResult<CustomerDto>> Update(
        int id, UpdateCustomerDto dto, CancellationToken ct)
    {
        var updated = await service.UpdateAsync(id, dto, ct);
        return updated is null ? NotFound() : Ok(updated);
    }

    [HttpDelete("{id:int}")]
    public async Task<IActionResult> Delete(int id, CancellationToken ct)
    {
        var deleted = await service.DeleteAsync(id, ct);
        return deleted ? NoContent() : NotFound();
    }
}
```

### React app bootstrap (once per solution)
```typescript
// ClientApp/src/main.tsx
import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import CustomerList from './pages/CustomerList/CustomerList';
import CustomerEdit from './pages/CustomerEdit/CustomerEdit';
import Layout from './components/Layout/Layout';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <Layout>
        <Routes>
          <Route path="/customers" element={<CustomerList />} />
          <Route path="/customers/add" element={<CustomerEdit />} />
          <Route path="/customers/edit/:id" element={<CustomerEdit />} />
          {/* Add route per .aspx page migrated */}
        </Routes>
      </Layout>
    </BrowserRouter>
  </React.StrictMode>
);
```

```typescript
// ClientApp/src/components/Layout/Layout.tsx
// Maps: Site.Master → Layout
import React from 'react';

export default function Layout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <nav className="navbar navbar-expand-lg navbar-dark bg-primary">
        <div className="container-fluid">
          <a className="navbar-brand" href="/">YourApp</a>
          <div className="navbar-nav">
            <a className="nav-link" href="/customers">Customers</a>
            {/* Add nav items matching MasterPage menu */}
          </div>
        </div>
      </nav>
      <main className="container-fluid mt-3">{children}</main>
    </>
  );
}
```

### package.json (once per solution)
```json
{
  "name": "yourapp-spa",
  "version": "1.0.0",
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "test": "vitest"
  },
  "dependencies": {
    "react": "^18.3.0",
    "react-dom": "^18.3.0",
    "react-router-dom": "^6.x"
  },
  "devDependencies": {
    "@types/react": "^18.x",
    "@types/react-dom": "^18.x",
    "typescript": "^5.x",
    "vite": "^5.x",
    "@vitejs/plugin-react": "^4.x",
    "vitest": "^1.x"
  }
}
```

### vite.config.ts (proxy API calls to .NET backend)
```typescript
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': { target: 'https://localhost:7001', secure: false },
      '/health': { target: 'https://localhost:7001', secure: false }
    }
  },
  build: { outDir: '../wwwroot', emptyOutDir: true }
});
```

## WebForms control → React map
| WebForms | React |
|---|---|
| `<asp:GridView>` | `<table>` + `.map()` + pagination state |
| `<asp:Repeater>` | `.map()` + JSX fragment |
| `<asp:UpdatePanel>` | useState + fetch (no full page reload) |
| `<asp:TextBox>` | `<input>` with `value` + `onChange` |
| `<asp:DropDownList>` | `<select>` with `value` + `onChange` |
| `<asp:Button>` | `<button type="submit">` or `onClick` handler |
| `<asp:CheckBox>` | `<input type="checkbox">` |
| `<asp:FileUpload>` | `<input type="file">` + FormData |
| `<asp:RequiredFieldValidator>` | HTML `required` + `errors` state |
| `<asp:ValidationSummary>` | Render `errors` object |
| `<asp:Label>` | `<label>` or `<span>` |
| `<asp:Literal>` | `{value}` inline |
| `Page_Load (!IsPostBack)` | `useEffect([], [])` |
| `Button_Click` | `onClick` handler or form `onSubmit` |
| `GridView_RowCommand` | `onClick` on row action button |
| `Response.Redirect("x.aspx")` | `window.location.href = '/x'` |
| `Session["key"]` | API call returns user context / JWT claims |
| ViewState | React state (`useState`) |
| MasterPage | Layout component wrapping `<Routes>` |
| `.ascx` UserControl | Separate React component |

## Session / auth in React
```typescript
// ViewState has no React equivalent — use component state
// Session["UserId"] → comes from JWT claims via API
// FormsAuthentication → OIDC redirects handled by backend middleware
// Protected routes check auth state:

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const [authed, setAuthed] = useState<boolean | null>(null);
  useEffect(() => {
    window.fetch('/api/auth/me')
      .then(r => setAuthed(r.ok))
      .catch(() => setAuthed(false));
  }, []);
  if (authed === null) return <div>Loading...</div>;
  if (!authed) { window.location.href = '/account/login'; return null; }
  return <>{children}</>;
}
```

## Map update
After generating component + API controller:
```
✅ DONE | WebApp | src/WebApp/Customer/List.aspx | [hash] | agent-spa-react | — | → ClientApp/pages/CustomerList
```
