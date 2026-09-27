@{
    RootModule = 'CADGrounded.Tools.psm1'
    ModuleVersion = '0.1.0'
    GUID = '0d9c4fa9-ae36-4eeb-99db-a0a3541590ef'
    Author = 'CADGrounded'
    CompanyName = 'CADGrounded'
    Copyright = '(c) CADGrounded project contributors'
    Description = 'Governed read-only engineering command surface for CADGrounded investigation workflows.'
    PowerShellVersion = '5.1'
    CompatiblePSEditions = @('Desktop','Core')
    FunctionsToExport = @(
        'Get-CGCapabilityCatalog',
        'Get-CGCapability',
        'Get-CGState',
        'Get-CGComponentBinding',
        'Test-CGContactPair',
        'Test-CGTopologyChain',
        'Get-CGMateBinding',
        'Get-CGRequiredBottleDOF',
        'Get-CGBottleContactConstraintMap',
        'Get-CGBottleContactWrenchRank',
        'Get-CGContactMaintenanceRequirements',
        'Get-CGCurrentPlan',
        'Get-CGInvestigationFrontier',
        'Invoke-CGRegisteredVerifier'
    )
    CmdletsToExport = @()
    VariablesToExport = @()
    AliasesToExport = @()
    PrivateData = @{
        PSData = @{
            Tags = @('CADGrounded','SOLIDWORKS','Engineering','PowerShell','Evidence')
            ProjectUri = 'https://github.com/anthonyedgar30000/Solidworks'
        }
    }
}
