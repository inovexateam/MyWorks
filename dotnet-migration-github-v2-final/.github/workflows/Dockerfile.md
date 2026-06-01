# Dockerfile — .NET 8 Production-Grade Multi-Stage Build
# Place this in the root of your solution

# ─── STAGE 1: Build ───────────────────────────────────────────────────────────
FROM mcr.microsoft.com/dotnet/sdk:8.0 AS build
WORKDIR /source

# Copy solution and project files first (layer caching — only re-run restore if .csproj changes)
COPY *.sln .
COPY Directory.Packages.props .
COPY src/Utilities/Utilities.csproj         src/Utilities/
COPY src/DAC/DAC.csproj                     src/DAC/
COPY src/BC/BC.csproj                       src/BC/
COPY src/SAC/SAC.csproj                     src/SAC/
COPY src/BPC/BPC.csproj                     src/BPC/
COPY src/WebApp/WebApp.csproj               src/WebApp/

# Restore with locked mode — guarantees package integrity
RUN dotnet restore --locked-mode

# Copy all source
COPY src/ src/

# Build release
RUN dotnet build src/WebApp/WebApp.csproj \
    --no-restore \
    --configuration Release

# Publish
RUN dotnet publish src/WebApp/WebApp.csproj \
    --no-build \
    --configuration Release \
    --output /app/publish \
    /p:UseAppHost=false \
    /p:PublishSingleFile=false

# ─── STAGE 2: Final Runtime ───────────────────────────────────────────────────
FROM mcr.microsoft.com/dotnet/aspnet:8.0 AS final

# Security: non-root user
RUN groupadd --gid 1000 appgroup && \
    useradd --uid 1000 --gid appgroup --shell /bin/bash --create-home appuser

WORKDIR /app

# Copy published output
COPY --from=build --chown=appuser:appgroup /app/publish .

# Security: remove write permissions from app files
RUN chmod -R 550 /app && \
    chmod -R 770 /app/logs 2>/dev/null || true

# Switch to non-root
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Expose port (non-privileged)
EXPOSE 8080

# Environment
ENV ASPNETCORE_URLS="http://+:8080"
ENV ASPNETCORE_ENVIRONMENT="Production"
ENV DOTNET_RUNNING_IN_CONTAINER=true

ENTRYPOINT ["dotnet", "WebApp.dll"]
