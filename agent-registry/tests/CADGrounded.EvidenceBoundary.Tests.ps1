BeforeAll {
    $repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
    $modulePath = Join-Path $repoRoot 'agent-registry/powershell/CADGrounded.Tools/CADGrounded.Tools.psd1'
    $sourcePath = Join-Path $repoRoot 'agent-registry/reasoning/runtime/function-first-bottle-contact-normal-map-evidence-20260927T082707281Z.json'
    $fixturePath = Join-Path $repoRoot ('agent-registry/reasoning/runtime/_pester-evidence-' + [guid]::NewGuid().ToString('N') + '.json')
    Import-Module $modulePath -Force
}

AfterAll {
    Remove-Item -LiteralPath $fixturePath -ErrorAction SilentlyContinue
    Remove-Module CADGrounded.Tools -ErrorAction SilentlyContinue
}

Describe 'Contact-normal evidence boundary' {
    It 'replays the admitted snapshot without asserting live freshness or mechanical acceptance' {
        $result = Get-CGBottleContactConstraintMap -EvidenceOnly
        $result.mechanical_acceptance_granted | Should -BeFalse
        $result.model_mutation | Should -BeFalse
        $result.write_authority | Should -BeExactly 'NONE'
        $result.data.freshness.mode | Should -BeExactly 'ADMITTED_SNAPSHOT_ONLY'
        $result.data.freshness.live_match | Should -BeNullOrEmpty
    }

    It 'rejects evidence whose source authority was replaced' {
        $record = Get-Content -LiteralPath $sourcePath -Raw | ConvertFrom-Json
        $record.source_authority = 'GENERAL_REFERENCE'
        $record | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath $fixturePath -Encoding UTF8
        { Get-CGBottleContactConstraintMap -EvidencePath $fixturePath -EvidenceOnly } |
            Should -Throw '*Unexpected source authority*'
    }

    It 'rejects a record that is no longer verified' {
        $record = Get-Content -LiteralPath $sourcePath -Raw | ConvertFrom-Json
        $record.evidence_state = 'HYPOTHETICAL'
        $record | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath $fixturePath -Encoding UTF8
        { Get-CGBottleContactConstraintMap -EvidencePath $fixturePath -EvidenceOnly } |
            Should -Throw '*not VERIFIED*'
    }

    It 'rejects evidence paths outside the repository' {
        { Get-CGBottleContactConstraintMap -EvidencePath $TestDrive -EvidenceOnly } |
            Should -Throw '*escaped the repository root*'
    }
}
