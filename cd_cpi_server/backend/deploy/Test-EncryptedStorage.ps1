# Run on each Windows host with the actual persistent and temporary storage paths.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string[]] $StoragePath
)

$ErrorActionPreference = 'Stop'
$checkedVolumes = @{}
foreach ($location in $StoragePath) {
    $item = Get-Item -LiteralPath $location -Force
    if ($item.PSProvider.Name -ne 'FileSystem' -or $item.FullName -notmatch '^[A-Za-z]:\\') {
        throw "Expected an existing local Windows storage path: $location"
    }
    $root = [System.IO.Path]::GetPathRoot($item.FullName)
    $component = $item
    while ($null -ne $component) {
        if ($component.Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
            throw "Verify the mounted or linked storage at its actual location: $location"
        }
        if ($component -is [System.IO.DirectoryInfo]) {
            $component = $component.Parent
        } else {
            $component = $component.Directory
        }
    }
    $mountPoint = $root.TrimEnd('\')
    if (-not $checkedVolumes.ContainsKey($mountPoint)) {
        $volume = Get-BitLockerVolume -MountPoint $mountPoint
        if ($volume.VolumeStatus -ne 'FullyEncrypted' -or $volume.ProtectionStatus -ne 'On') {
            throw "BitLocker is not fully encrypted with protection on for $mountPoint"
        }
        $checkedVolumes[$mountPoint] = $true
    }
    Write-Output "Encrypted volume confirmed for $location"
}
