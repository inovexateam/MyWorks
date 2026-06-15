# Java / Spring — Design-Focused Analyzer Setup

## 1. SonarLint (IDE) + SonarQube/Sonar Cloud (CI)

Install SonarLint plugin in IntelliJ/VS Code. It flags many of the design
issues live: god classes (`S1448` too many methods), cognitive complexity
(`S3776`), exception handling (`S1166`, `S2139`), resource leaks (`S2095`),
DI issues, and more — Copilot can then explain *why* each finding matters
and propose the fix.

## 2. ArchUnit — enforce layering and dependency direction

```xml
<!-- pom.xml -->
<dependency>
    <groupId>com.tngtech.archunit</groupId>
    <artifactId>archunit-junit5</artifactId>
    <version>1.3.0</version>
    <scope>test</scope>
</dependency>
```

```java
// src/test/java/com/example/ArchitectureTest.java
import com.tngtech.archunit.core.importer.ClassFileImporter;
import com.tngtech.archunit.lang.ArchRule;
import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.classes;
import static com.tngtech.archunit.library.Architectures.layeredArchitecture;

class ArchitectureTest {

    private final var importedClasses = new ClassFileImporter()
            .importPackages("com.example.myapp");

    @Test
    void layered_architecture_is_respected() {
        ArchRule rule = layeredArchitecture()
            .consideringAllDependencies()
            .layer("Controller").definedBy("..controller..")
            .layer("Service").definedBy("..service..")
            .layer("Repository").definedBy("..repository..")
            .layer("Domain").definedBy("..domain..")

            .whereLayer("Controller").mayNotBeAccessedByAnyLayer()
            .whereLayer("Service").mayOnlyBeAccessedByLayers("Controller")
            .whereLayer("Repository").mayOnlyBeAccessedByLayers("Service")
            .whereLayer("Domain").mayOnlyBeAccessedByLayers("Service", "Repository");

        rule.check(importedClasses);
    }

    @Test
    void controllers_should_not_use_repositories_directly() {
        ArchRule rule = classes().that().resideInAPackage("..controller..")
            .should().notDependOnClassesThat().resideInAPackage("..repository..");

        rule.check(importedClasses);
    }

    @Test
    void domain_should_not_depend_on_spring_framework() {
        ArchRule rule = classes().that().resideInAPackage("..domain..")
            .should().notDependOnClassesThat()
            .resideInAnyPackage("org.springframework..");

        rule.check(importedClasses);
    }

    @Test
    void services_should_be_annotated_and_not_use_field_injection() {
        ArchRule rule = noFields()
            .should().beAnnotatedWith("org.springframework.beans.factory.annotation.Autowired");

        rule.check(importedClasses);
    }
}
```

## 3. Spring bean scope / lifetime checks

Add a quick rule of thumb to your `copilot-instructions.md` review (already
included): flag any `@Component`/`@Service` (default singleton) that injects
a `@RequestScope` or `@SessionScope` bean directly without a `ObjectFactory`
or proxy — this is the Java equivalent of the .NET singleton-holding-scoped
problem.

## 4. JPA / Hibernate N+1 detection

- Enable `spring.jpa.properties.hibernate.generate_statistics=true` and
  log `org.hibernate.stat` at `DEBUG` in dev to spot repeated query patterns.
- Or add the **db-util** / **JPA Buddy** plugin which highlights N+1 risks
  in entity relationship mappings (`@OneToMany` without `fetch =
  FetchType.LAZY` + batch fetching configured).
