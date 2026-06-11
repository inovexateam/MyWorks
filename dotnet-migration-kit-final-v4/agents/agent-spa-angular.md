# Agent: WebForms → Angular 17+ + TypeScript

## Identity
Converts .aspx pages to Angular standalone components with TypeScript.
Works from AST JSON — never re-reads .aspx files directly.
Generates: component, service, model, module route, API controller.

## Pre-work
1. Check CODEBASE-MAP.md hash — skip ✅ DONE
2. Read .github/memory/ast/[PageName].json (run agent-roslyn-ast first)
3. Never re-read the .aspx file if AST exists

## What gets generated per screen

### File structure
```
src-core/WebApp.Core/ClientApp/src/
├── app/
│   ├── features/
│   │   └── [feature-name]/
│   │       ├── [page-name]/
│   │       │   ├── [page-name].component.ts
│   │       │   ├── [page-name].component.html
│   │       │   └── [page-name].component.spec.ts
│   │       ├── [feature-name].service.ts
│   │       └── [feature-name].routes.ts
│   ├── shared/
│   │   ├── models/[feature-name].model.ts
│   │   └── components/layout/layout.component.ts
│   └── app.routes.ts
└── index.html
```

---

## TypeScript models (from ast.dataBindings[])
```typescript
// shared/models/customer.model.ts
export interface Customer {
  id: number;
  name: string;
  email: string;
  status: 'Active' | 'Inactive';
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

## Service (from ast.apiEndpoints[])
```typescript
// features/customers/customers.service.ts
import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import type { Customer, CustomerListParams, PagedResult } from '../../shared/models/customer.model';

@Injectable({ providedIn: 'root' })
export class CustomerService {
  private http = inject(HttpClient);
  private base = '/api/customers';

  getAll(params: CustomerListParams): Observable<PagedResult<Customer>> {
    let p = new HttpParams();
    if (params.search) p = p.set('search', params.search);
    if (params.status) p = p.set('status', params.status);
    if (params.page)   p = p.set('page', params.page);
    if (params.pageSize) p = p.set('pageSize', params.pageSize);
    return this.http.get<PagedResult<Customer>>(this.base, { params: p });
  }

  getById(id: number): Observable<Customer> {
    return this.http.get<Customer>(`${this.base}/${id}`);
  }

  create(dto: Partial<Customer>): Observable<Customer> {
    return this.http.post<Customer>(this.base, dto);
  }

  update(id: number, dto: Partial<Customer>): Observable<Customer> {
    return this.http.put<Customer>(`${this.base}/${id}`, dto);
  }

  delete(id: number): Observable<void> {
    return this.http.delete<void>(`${this.base}/${id}`);
  }
}
```

## List component (GridView + Search + UpdatePanel pattern)

```typescript
// features/customers/customer-list/customer-list.component.ts
import { Component, inject, signal, computed, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { CustomerService } from '../customers.service';
import type { Customer, CustomerListParams, PagedResult } from '../../../shared/models/customer.model';

@Component({
  selector: 'app-customer-list',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './customer-list.component.html'
})
export class CustomerListComponent implements OnInit {
  private svc = inject(CustomerService);
  private router = inject(Router);

  // Maps: TextBox txtSearch
  searchTerm = signal('');
  statusFilter = signal('');

  // Maps: GridView data
  result = signal<PagedResult<Customer> | null>(null);
  loading = signal(false);
  error = signal<string | null>(null);
  currentPage = signal(1);
  pageSize = 20;

  totalPages = computed(() =>
    Math.ceil((this.result()?.totalCount ?? 0) / this.pageSize));

  ngOnInit() { this.load(); }

  // Maps: Page_Load(!IsPostBack)
  load() {
    this.loading.set(true);
    const params: CustomerListParams = {
      search: this.searchTerm(),
      status: this.statusFilter(),
      page: this.currentPage(),
      pageSize: this.pageSize
    };
    this.svc.getAll(params).subscribe({
      next: data => { this.result.set(data); this.loading.set(false); },
      error: e  => { this.error.set(e.message); this.loading.set(false); }
    });
  }

  // Maps: btnSearch_Click
  onSearch() { this.currentPage.set(1); this.load(); }

  // Maps: btnAdd_Click
  onAdd() { this.router.navigate(['/customers/add']); }

  // Maps: gvCustomers_RowCommand "Edit"
  onEdit(id: number) { this.router.navigate(['/customers/edit', id]); }

  // Maps: gvCustomers_RowCommand "Delete"
  onDelete(id: number) {
    if (!confirm('Delete this customer?')) return;
    this.svc.delete(id).subscribe({ next: () => this.load() });
  }

  onPageChange(page: number) { this.currentPage.set(page); this.load(); }

  pages() { return Array.from({ length: this.totalPages() }, (_, i) => i + 1); }
}
```

```html
<!-- customer-list.component.html -->
<div class="container-fluid">
  <h2>Customer List</h2>

  <!-- Maps: TextBox txtSearch + Button btnSearch -->
  <div class="row g-2 mb-3">
    <div class="col-auto">
      <input [(ngModel)]="searchTerm" class="form-control" placeholder="Search..."
             (keyup.enter)="onSearch()" />
    </div>
    <div class="col-auto">
      <button (click)="onSearch()" class="btn btn-primary">Search</button>
    </div>
    <div class="col-auto">
      <button (click)="onAdd()" class="btn btn-success">Add New</button>
    </div>
  </div>

  <!-- Error -->
  <div *ngIf="error()" class="alert alert-danger">{{ error() }}</div>

  <!-- Loading spinner — replaces UpdatePanel progress -->
  <div *ngIf="loading()" class="text-center">
    <div class="spinner-border"></div>
  </div>

  <!-- Maps: GridView gvCustomers -->
  <table *ngIf="!loading() && result()" class="table table-striped table-hover">
    <thead>
      <tr><th>Name</th><th>Email</th><th>Status</th><th>Actions</th></tr>
    </thead>
    <tbody>
      <tr *ngFor="let c of result()!.items">
        <td>{{ c.name }}</td>
        <td>{{ c.email }}</td>
        <td>
          <span [class]="'badge bg-' + (c.status === 'Active' ? 'success' : 'secondary')">
            {{ c.status }}
          </span>
        </td>
        <td>
          <button (click)="onEdit(c.id)" class="btn btn-sm btn-outline-primary me-1">Edit</button>
          <button (click)="onDelete(c.id)" class="btn btn-sm btn-outline-danger">Delete</button>
        </td>
      </tr>
    </tbody>
  </table>

  <!-- Pagination — replaces GridView AllowPaging -->
  <nav *ngIf="totalPages() > 1">
    <ul class="pagination">
      <li *ngFor="let p of pages()" [class.active]="p === currentPage()" class="page-item">
        <button (click)="onPageChange(p)" class="page-link">{{ p }}</button>
      </li>
    </ul>
  </nav>
</div>
```

## Form / Edit component pattern
```typescript
// customer-edit.component.ts
import { Component, inject, signal, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { CustomerService } from '../customers.service';

@Component({
  selector: 'app-customer-edit',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './customer-edit.component.html'
})
export class CustomerEditComponent implements OnInit {
  private svc = inject(CustomerService);
  private route = inject(ActivatedRoute);
  private router = inject(Router);

  id = signal<number | null>(null);
  form = signal({ name: '', email: '', status: 'Active' });
  errors = signal<Record<string, string>>({});
  saving = signal(false);
  get isEdit() { return this.id() !== null; }

  ngOnInit() {
    const id = this.route.snapshot.paramMap.get('id');
    if (id) {
      this.id.set(+id);
      this.svc.getById(+id).subscribe(c => this.form.set({ ...c }));
    }
  }

  onSubmit() {
    this.saving.set(true);
    const op = this.isEdit
      ? this.svc.update(this.id()!, this.form())
      : this.svc.create(this.form());
    op.subscribe({
      next: () => this.router.navigate(['/customers']),
      error: e => {
        this.errors.set(e.error?.errors ?? {});
        this.saving.set(false);
      }
    });
  }

  onCancel() { this.router.navigate(['/customers']); }
}
```

```html
<!-- customer-edit.component.html -->
<div class="container">
  <h2>{{ isEdit ? 'Edit' : 'Add' }} Customer</h2>
  <form (ngSubmit)="onSubmit()" #f="ngForm" class="row g-3">
    <div class="col-md-6">
      <label class="form-label">Name</label>
      <input [(ngModel)]="form().name" name="name" required maxlength="200"
             [class.is-invalid]="errors()['Name']" class="form-control" />
      <div *ngIf="errors()['Name']" class="invalid-feedback">{{ errors()['Name'] }}</div>
    </div>
    <div class="col-md-6">
      <label class="form-label">Email</label>
      <input [(ngModel)]="form().email" name="email" type="email" required
             [class.is-invalid]="errors()['Email']" class="form-control" />
      <div *ngIf="errors()['Email']" class="invalid-feedback">{{ errors()['Email'] }}</div>
    </div>
    <div class="col-md-4">
      <label class="form-label">Status</label>
      <select [(ngModel)]="form().status" name="status" class="form-select">
        <option>Active</option><option>Inactive</option>
      </select>
    </div>
    <div class="col-12">
      <button type="submit" [disabled]="saving()" class="btn btn-primary me-2">
        {{ saving() ? 'Saving...' : 'Save' }}
      </button>
      <button type="button" (click)="onCancel()" class="btn btn-secondary">Cancel</button>
    </div>
  </form>
</div>
```

## Routing (from all .aspx pages)
```typescript
// app.routes.ts
import { Routes } from '@angular/router';
import { authGuard } from './shared/guards/auth.guard';

export const routes: Routes = [
  { path: '', redirectTo: '/customers', pathMatch: 'full' },
  {
    path: 'customers',
    canActivate: [authGuard],
    children: [
      { path: '', loadComponent: () => import('./features/customers/customer-list/customer-list.component').then(m => m.CustomerListComponent) },
      { path: 'add', loadComponent: () => import('./features/customers/customer-edit/customer-edit.component').then(m => m.CustomerEditComponent) },
      { path: 'edit/:id', loadComponent: () => import('./features/customers/customer-edit/customer-edit.component').then(m => m.CustomerEditComponent) }
    ]
  }
  // Add one route group per .aspx page set
];
```

## App bootstrap (once per solution)
```typescript
// main.ts
import { bootstrapApplication } from '@angular/platform-browser';
import { provideRouter } from '@angular/router';
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { csrfInterceptor } from './app/shared/interceptors/csrf.interceptor';
import { AppComponent } from './app/app.component';
import { routes } from './app/app.routes';

bootstrapApplication(AppComponent, {
  providers: [
    provideRouter(routes),
    provideHttpClient(withInterceptors([csrfInterceptor]))
  ]
});
```

```typescript
// shared/interceptors/csrf.interceptor.ts
import { HttpInterceptorFn } from '@angular/common/http';

export const csrfInterceptor: HttpInterceptorFn = (req, next) => {
  const token = document.querySelector<HTMLMetaElement>('meta[name="csrf-token"]')?.content;
  if (token && ['POST','PUT','PATCH','DELETE'].includes(req.method)) {
    return next(req.clone({ headers: req.headers.set('RequestVerificationToken', token) }));
  }
  return next(req);
};
```

## package.json (once per solution)
```json
{
  "name": "yourapp-angular",
  "version": "1.0.0",
  "scripts": {
    "ng": "ng",
    "start": "ng serve --proxy-config proxy.conf.json",
    "build": "ng build --output-path ../wwwroot",
    "test": "ng test --watch=false"
  },
  "dependencies": {
    "@angular/animations": "^17.x",
    "@angular/common": "^17.x",
    "@angular/compiler": "^17.x",
    "@angular/core": "^17.x",
    "@angular/forms": "^17.x",
    "@angular/platform-browser": "^17.x",
    "@angular/platform-browser-dynamic": "^17.x",
    "@angular/router": "^17.x",
    "rxjs": "^7.x",
    "zone.js": "^0.x"
  },
  "devDependencies": {
    "@angular/cli": "^17.x",
    "@angular/compiler-cli": "^17.x",
    "typescript": "^5.x"
  }
}
```

## proxy.conf.json (dev only — proxy to .NET backend)
```json
{
  "/api": { "target": "https://localhost:7001", "secure": false },
  "/health": { "target": "https://localhost:7001", "secure": false }
}
```

## WebForms → Angular map
| WebForms | Angular |
|---|---|
| `<asp:GridView>` | `<table *ngFor>` + pagination component |
| `<asp:UpdatePanel>` | Component re-renders automatically on signal change |
| `<asp:TextBox>` | `<input [(ngModel)]>` |
| `<asp:DropDownList>` | `<select [(ngModel)]>` |
| `<asp:Button>` | `<button (click)="">` or `<button type="submit">` |
| `<asp:CheckBox>` | `<input type="checkbox" [(ngModel)]>` |
| `<asp:RequiredFieldValidator>` | `required` attribute + template ref variable |
| `<asp:ValidationSummary>` | `*ngIf="errors()"` error display block |
| `Page_Load(!IsPostBack)` | `ngOnInit()` |
| `Button_Click` | `(click)` binding or `(ngSubmit)` |
| `GridView_RowCommand` | `(click)` on row button calling component method |
| `Response.Redirect("x.aspx")` | `this.router.navigate(['/x'])` |
| `Session["key"]` | JWT claims via HttpClient `/api/auth/me` |
| ViewState | Component signals / state |
| MasterPage | `AppComponent` layout + `<router-outlet>` |
| `.ascx` UserControl | Standalone Angular component |

## Map update
```
✅ DONE | WebApp | src/WebApp/Customer/List.aspx | [hash] | agent-spa-angular | — | → ClientApp/features/customers
```
