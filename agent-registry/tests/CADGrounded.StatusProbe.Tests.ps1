BeforeAll {
    $repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
    Import-Module (Join-Path $repoRoot 'agent-registry/powershell/CADGrounded.Tools/CADGrounded.Tools.psd1') -Force

    function New-FakeStatusRun {
        param([string]$Document = 'IXOR_Benchmark_v43_PRISM_OPERATING_CANDIDATE_PORTABLE')
        $envelope = @{
            ok = $true
            command_id = 'sw.status'
            source_classification = 'verified_from_solidworks_api'
            data = @{
                worker_version = '0.4.4'
                write_authority = 'NONE'
                solidworks_process_id = 1234
                document = @{
                    title = $Document
                    path = 'C:\CAD\IXOR_Benchmark_v43_PRISM_OPERATING_CANDIDATE_PORTABLE.SLDASM'
                    type = 'assembly'
                    active_configuration = 'V43_WRAP'
                    save_flag = $false
                }
            }
        }
        return [pscustomobject]@{
            outcome = 'EXITED'
            process_id = 9988
            exit_code = 0
            stdout = ($envelope | ConvertTo-Json -Depth 10 -Compress)
            stderr = ''
        }
    }
}

AfterAll {
    Remove-Variable -Name CGStatusRuns,CGFileStates -Scope Global -ErrorAction SilentlyContinue
    Remove-Module CADGrounded.Tools -ErrorAction SilentlyContinue
}

Describe 'Bounded sw.status process recovery' {
    BeforeEach {
        $global:CGStatusRuns = [System.Collections.Queue]::new()
        Mock Invoke-CGStatusProcess -ModuleName CADGrounded.Tools {
            $global:CGStatusRuns.Dequeue()
        }
    }

    It 'retries once only after the timed-out worker was terminated' {
        $global:CGStatusRuns.Enqueue([pscustomobject]@{ outcome = 'TIMEOUT_TERMINATED'; process_id = 9987 })
        $global:CGStatusRuns.Enqueue((New-FakeStatusRun))
        $status = InModuleScope CADGrounded.Tools { Invoke-CGStatusProbe -TimeoutMilliseconds 1000 }
        $status.status_probe.outcome | Should -BeExactly 'RECOVERED_AFTER_TIMEOUT'
        $status.status_probe.attempts | Should -Be 2
        $global:CGStatusRuns.Count | Should -Be 0
        Should -Invoke Invoke-CGStatusProcess -ModuleName CADGrounded.Tools -Exactly -Times 2
    }

    It 'stops after two confirmed terminated timeouts' {
        $global:CGStatusRuns.Enqueue([pscustomobject]@{ outcome = 'TIMEOUT_TERMINATED'; process_id = 9987 })
        $global:CGStatusRuns.Enqueue([pscustomobject]@{ outcome = 'TIMEOUT_TERMINATED'; process_id = 9988 })
        { InModuleScope CADGrounded.Tools { Invoke-CGStatusProbe -TimeoutMilliseconds 1000 } } |
            Should -Throw '*timed out twice*'
        Should -Invoke Invoke-CGStatusProcess -ModuleName CADGrounded.Tools -Exactly -Times 2
    }

    It 'does not retry when the worker reports no active document' {
        $global:CGStatusRuns.Enqueue([pscustomobject]@{
            outcome = 'EXITED'; process_id = 9988; exit_code = 1; stderr = ''
            stdout = '{"ok":false,"command_id":"sw.status","error":{"type":"no_active_document"}}'
        })
        { InModuleScope CADGrounded.Tools { Invoke-CGStatusProbe -TimeoutMilliseconds 1000 } } |
            Should -Throw '*no_active_document*retry blocked*'
        Should -Invoke Invoke-CGStatusProcess -ModuleName CADGrounded.Tools -Exactly -Times 1
    }

    It 'rejects a successful envelope with no active document' {
        $global:CGStatusRuns.Enqueue([pscustomobject]@{
            outcome = 'EXITED'; process_id = 9988; exit_code = 0; stderr = ''
            stdout = '{"ok":true,"command_id":"sw.status","source_classification":"verified_from_solidworks_api","data":{"write_authority":"NONE","solidworks_process_id":1234,"document":null}}'
        })
        { InModuleScope CADGrounded.Tools { Invoke-CGStatusProbe -TimeoutMilliseconds 1000 } } |
            Should -Throw '*lacks an exact active document*'
        Should -Invoke Invoke-CGStatusProcess -ModuleName CADGrounded.Tools -Exactly -Times 1
    }

    It 'blocks a second attempt if a timed-out worker was not confirmed terminated' {
        $global:CGStatusRuns.Enqueue([pscustomobject]@{ outcome = 'TIMEOUT_UNCONFIRMED'; process_id = 9988 })
        { InModuleScope CADGrounded.Tools { Invoke-CGStatusProbe -TimeoutMilliseconds 1000 } } |
            Should -Throw '*retry blocked*'
        Should -Invoke Invoke-CGStatusProcess -ModuleName CADGrounded.Tools -Exactly -Times 1
    }

    It 'binds a stable file hash to two matching status reads' {
        $global:CGStatusRuns.Enqueue((New-FakeStatusRun))
        $global:CGStatusRuns.Enqueue((New-FakeStatusRun))
        $global:CGFileStates = [System.Collections.Queue]::new()
        $global:CGFileStates.Enqueue([ordered]@{ length = 42; last_write_time_utc = '2026-09-27T08:00:00Z'; sha256 = ('a' * 64) })
        $global:CGFileStates.Enqueue([ordered]@{ length = 42; last_write_time_utc = '2026-09-27T08:00:00Z'; sha256 = ('a' * 64) })
        Mock Get-CGFileState -ModuleName CADGrounded.Tools { $global:CGFileStates.Dequeue() }
        $result = Get-CGState -ExpectedConfiguration 'V43_WRAP'
        $result.data.file_state.sha256 | Should -BeExactly ('a' * 64)
        $result.data.status_probes.Count | Should -Be 2
        $result.mechanical_acceptance_granted | Should -BeFalse
        Should -Invoke Get-CGFileState -ModuleName CADGrounded.Tools -Exactly -Times 2
    }

    It 'rejects document drift during the file-hash readback' {
        $global:CGStatusRuns.Enqueue((New-FakeStatusRun))
        $global:CGStatusRuns.Enqueue((New-FakeStatusRun -Document 'OTHER_DOCUMENT'))
        Mock Get-CGFileState -ModuleName CADGrounded.Tools {
            [ordered]@{ length = 42; last_write_time_utc = '2026-09-27T08:00:00Z'; sha256 = ('a' * 64) }
        }
        { Get-CGState -ExpectedConfiguration 'V43_WRAP' } | Should -Throw '*changed during status readback*'
    }

    It 'rejects a changed assembly file hash during status readback' {
        $global:CGStatusRuns.Enqueue((New-FakeStatusRun))
        $global:CGStatusRuns.Enqueue((New-FakeStatusRun))
        $global:CGFileStates = [System.Collections.Queue]::new()
        $global:CGFileStates.Enqueue([ordered]@{ length = 42; last_write_time_utc = '2026-09-27T08:00:00Z'; sha256 = ('a' * 64) })
        $global:CGFileStates.Enqueue([ordered]@{ length = 42; last_write_time_utc = '2026-09-27T08:00:00Z'; sha256 = ('b' * 64) })
        Mock Get-CGFileState -ModuleName CADGrounded.Tools { $global:CGFileStates.Dequeue() }
        { Get-CGState -ExpectedConfiguration 'V43_WRAP' } | Should -Throw '*changed during status readback*'
    }
}
