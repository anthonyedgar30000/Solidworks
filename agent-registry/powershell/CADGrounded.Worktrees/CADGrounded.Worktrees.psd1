@{
    RootModule = 'CADGrounded.Worktrees.psm1'
    ModuleVersion = '0.1.0'
    GUID = 'dcdb0b1e-0d6a-4d83-91c6-9bdab91a6e27'
    Author = 'CADGrounded'
    CompanyName = 'CADGrounded'
    Copyright = '(c) CADGrounded project contributors'
    Description = 'Governed sparse Git worktree lifecycle and evidence-preserving retirement for CADGrounded repositories.'
    PowerShellVersion = '5.1'
    CompatiblePSEditions = @('Desktop','Core')
    FunctionsToExport = @(
        'New-CADGroundedWorktree',
        'Get-CADGroundedWorktreeStatus',
        'Test-CADGroundedWorktreeRetirement',
        'Remove-CADGroundedWorktree'
    )
    CmdletsToExport = @()
    VariablesToExport = @()
    AliasesToExport = @()
    PrivateData = @{
        PSData = @{
            Tags = @('CADGrounded','Git','Worktree','Governance','Evidence','PowerShell')
            ProjectUri = 'https://github.com/anthonyedgar30000/Solidworks'
        }
    }
}
