param(
    [string[]]$Exclude = @(".git", "venv", "__pycache__", ".pytest_cache", ".mypy_cache")
)

function Show-Tree {
    param([string]$Path, [string]$Indent = "")

    $items = Get-ChildItem $Path | Where-Object {
        foreach ($e in $Exclude) { if ($_.FullName -like "*\$e*") { return $false } }
        return $true
    }

    foreach ($item in $items) {
        Write-Output "$Indent|-- $($item.Name)"
        if ($item.PSIsContainer) {
            Show-Tree -Path $item.FullName -Indent "$Indent   "
        }
    }
}

Show-Tree -Path (Get-Location) | Out-File -Encoding utf8 "structure_clean.txt"
