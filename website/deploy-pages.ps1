# Build the Docusaurus site and publish it to the Codeberg Pages `pages` branch.
# No CI runner required — uses your local git credentials.
#
#   pwsh website/deploy-pages.ps1
#
# Serves at https://phoenixadultprovider.codeberg.page/PhoenixAdult/

$ErrorActionPreference = 'Stop'

$repoUrl = 'https://codeberg.org/PhoenixAdultProvider/PhoenixAdult.git'
$websiteDir = $PSScriptRoot
$buildDir = Join-Path $websiteDir 'build'

Push-Location $websiteDir
try {
    if (-not (Test-Path (Join-Path $websiteDir 'node_modules'))) {
        npm ci
    }
    npm run build

    Push-Location $buildDir
    try {
        # Fresh orphan history each deploy keeps the pages branch tiny.
        if (Test-Path '.git') { Remove-Item -Recurse -Force '.git' }
        git init -q
        git checkout -q -b pages
        git add -A
        git -c user.name='deploy' -c user.email='deploy@local' commit -q -m "Deploy site"
        git push -f $repoUrl pages
    }
    finally {
        if (Test-Path '.git') { Remove-Item -Recurse -Force '.git' }
        Pop-Location
    }
    Write-Host '[deploy] pushed to pages branch -> https://phoenixadultprovider.codeberg.page/PhoenixAdult/' -ForegroundColor Green
}
finally {
    Pop-Location
}
