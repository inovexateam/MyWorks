# Skill: Pattern Recognition

## Identity
You are a .NET architectural pattern recognition engine. You identify design patterns, anti-patterns, and idioms in ASP.NET Framework code and map each to its idiomatic .NET Core equivalent.

## Trigger Conditions
- `agent-code-refactor` encounters unfamiliar code structure
- `agent-ui-adapter` needs to categorize a UI control
- Code analysis returns ambiguous pattern signals
- A class has complex interactions that don't fit standard categories

---

## WebForms → Core UI Pattern Map

### Page Lifecycle Patterns
```
Framework                          Core Equivalent
─────────────────────────────────────────────────
Page_Load (GET)               →    OnGet() in PageModel
Page_Load (postback check)    →    OnPost() in PageModel
Page_PreRender                →    Filter / ViewResult logic
Page_Init                     →    Constructor injection
Page_Unload                   →    IDisposable / using
IsPostBack check              →    HTTP method check (GET/POST)
```

### Control Event Patterns
```
Framework                          Core Equivalent
─────────────────────────────────────────────────
Button_Click                  →    OnPost() handler
GridView_RowCommand           →    POST with row id parameter
DropDownList_SelectedIndex    →    AJAX endpoint / form POST
Timer_Tick                    →    JavaScript setInterval + API
FileUpload control            →    IFormFile parameter
```

### Data Binding Patterns
```
Framework                          Core Equivalent
─────────────────────────────────────────────────
GridView.DataSource + DataBind →   @foreach in .cshtml
Repeater                      →    @foreach with partial view
DataList                      →    CSS Grid + @foreach
ListView                      →    Custom Razor template
FormView (insert/edit/delete) →    CRUD Razor Pages
DetailsView                   →    Detail Razor Page
ObjectDataSource              →    Direct service injection
SqlDataSource                 →    Remove entirely — use service layer
```

### Navigation Patterns
```
Framework                          Core Equivalent
─────────────────────────────────────────────────
Response.Redirect             →    RedirectToAction / RedirectToPage
Server.Transfer               →    Rewrite middleware / forward
SiteMap / Menu control        →    Tag helpers / Razor navigation partial
Breadcrumb                    →    Custom ViewComponent
```

---

## Service Layer Patterns

### Dependency Injection Anti-Patterns
```csharp
// ❌ Service Locator (remove this)
var service = ServiceLocator.Current.GetInstance<IUserService>();

// ❌ Static factory (remove this)
var service = ServiceFactory.Create<IUserService>();

// ❌ Direct new (for services that should be injected)
var service = new UserService(new UserRepository());

// ✅ Constructor injection
public class UserController : Controller {
    private readonly IUserService _userService;
    public UserController(IUserService userService) {
        _userService = userService;
    }
}
```

### Repository Pattern Migrations
```csharp
// Framework — EF6 repository
public class UserRepository : IUserRepository {
    private readonly MyContext _context = new MyContext(); // ❌ no DI
    
    public User GetById(int id) {
        return _context.Users.Find(id);
    }
}

// Core — EF Core repository  
public class UserRepository : IUserRepository {
    private readonly AppDbContext _context;
    
    public UserRepository(AppDbContext context) { // ✅ injected
        _context = context;
    }
    
    public async Task<User?> GetByIdAsync(int id) { // ✅ async
        return await _context.Users.FindAsync(id);
    }
}
```

---

## How Agents Use This Skill

```
Load: skills/pattern-recognition.md
TARGET: [file or code snippet]
PATTERN_TYPE: [ui | service | data | security | async]
OUTPUT: [mapping | refactored-code | risk-assessment]
```
