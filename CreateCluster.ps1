Param (
    [Parameter(Mandatory=$true, Position=0, HelpMessage="Number of Nodes to create")]
    [int]$nodes,

    [Parameter(Mandatory=$true, Position=1, HelpMessage="OVA File to Deploy")]
    [string]$ovaFile,

    [Parameter(Mandatory=$true, Position=2, HelpMessage="Node IPs to assign")]
    [string[]]$ipAddrs,

    [string]$vCenterServer,
    [string]$clusterName = "VM Cluster",
    [string]$dsPrefix = "General *",
    [string]$cloudConfig = "./cloud-config.yml",
    [string]$keyDir = "./authorized_keys",
    [string]$ovfDefaults,

    [string]$discoveryURL = "https://discovery.etcd.io"
)

$root = Split-Path $MyInvocation.MyCommand.Path
$randomName = $root + "\RandomName.ps1"

################################################################################
#

Function ReadDefaultProperties {
    Param (
        [Parameter(Mandatory=$true, Position=0)]
        [string]$path
    )

    $props = @{}

    if ($path -And (Test-Path $path)) {
        $dc = Get-Content $path -raw | ConvertFrom-StringData

        if ($dc['network']) { $props['NetworkMapping.VM Network'] = $dc['network'] }

        $dcgi = $dc.GetEnumerator() | Where {-not ($_.Name -eq "network")}

        ForEach ($p in $dcgi) {
            $props.add("guestinfo." + $p.Name, $p.Value)
        }
    }

    return $props
}

Function GetKeysFromDir {
    Param (
        [Parameter(Mandatory=$true, Position=0)]
        [string]$dir
    )

    $keys = @()

    ForEach ($k in Get-ChildItem $dir -Filter *.pub) {
        $keys += Get-Content $k.FullName
    }

    return $keys
}

Function EncodeCloudConfig {
    Param (
        [Parameter(Mandatory=$true, Position=0)]
        [string]$path,

        [Parameter(Mandatory=$true, Position=1)]
        [string[]]$keys
    )

    if (!(Test-Path $path)) {
        Throw "Invalid cloud config path" + ", '" + $path + "' does not exist"
    }

    $cc = Get-Content $path -raw
    $cc += "`n" + "ssh_authorized_keys:`n"

    ForEach ($k in $keys) {
        $cc += '  - "' + $k + '"'
    }

    $ccb = [System.Text.Encoding]::UTF8.GetBytes($cc)
    return [System.Convert]::ToBase64String($ccb)
}

Function NewClusterID {
    Param (
        [Parameter(Mandatory=$true, Position=0)]
        [int]$nodes
    )

    $uri = (Invoke-WebRequest ($discoveryURL + "/new?size=" + $nodes)).Content
    return $uri.Split("/")[-1]
}

Function ClusterDiscoveryURL {
    Param (
        [Parameter(Mandatory=$true, Position=0, ValueFromPipeline=$true)]
        [string]$clusterID
    )

    return ($discoveryURL + "/" + $clusterID)
}

Function NewNodeNames {
    Param (
        [Parameter(Mandatory=$true, Position=0)]
        [int]$count
    )

    $vms = Get-VM
    $vmNames = $vms | % {$_.Name.Split('.')[0]} | Sort | Get-Unique
    $knownVms = @{}
    ForEach ($n in $vmNames) {$knownVms.add($n, $TRUE)}

    $nodeNames = @{}
    For ($i = 0; $i -lt $count; $i++) {
        $name = invoke-expression $randomName

        While ($knownVms[$name] -Or $nodeNames[$name]) {
            $name = invoke-expression $randomName
        }

        $nodeNames[$name] = $true
    }

    return $nodeNames.Keys | Sort
}

################################################################################
#

Function ConvertTo-DecimalIP {
    Param (
        [Parameter(Mandatory=$true, Position=0)]
        [Net.IPAddress]$ip
    )

    $i = 3
    $d = 0

    ForEach ($b in $ip.GetAddressBytes()) {
        $d += $b * [Math]::Pow(256, $i)
        $i -= 1
    }

    return [UInt32]$d
}

Function ConvertTo-IP {
    Param (
        [Parameter(Mandatory=$true, Position=0)]
        [UInt32]$addr
    )

    $segments = $(
        For ($i = 3; $i -gt -1; $i--) {
            $rem = $addr % [Math]::Pow(256, $i)
            ($addr - $rem) / [Math]::Pow(256, $i)
            $addr = $rem
        }
    )

    return [Net.IPAddress]([String]::Join('.', $segments))
}

Function ConvertTo-IPAddrs {
    Param (
        [Parameter(Mandatory=$true, Position=0, ValueFromPipeline=$true)]
        [string[]]$ips
    )

    $addrs = @()

    ForEach ($ip in $ips) {
        if ($ip.Contains("-")) {
            $ipRange = $ip.Split("-") | % {[Net.IPAddress]$_}
            $lowest = ConvertTo-DecimalIP $ipRange[0]
            $highest = ConvertTo-DecimalIP $ipRange[-1]

            For ($i = $lowest; $i -le $highest; $i++) {
                $addrs += ConvertTo-IP $i
            }
        }
        else {
            $addrs += [Net.IPAddress]$ip
        }
    }

    return ,$addrs
}

Function Select-IPs {
    Param (
        [Parameter(Mandatory=$true, Position=0, ValueFromPipeline=$true)]
        [Net.IPAddress[]]$addrs,

        [Parameter(Mandatory=$true, Position=1)]
        [int]$limit
    )

    if ($addrs.Count -lt $limit) {
        Throw "Not enough IPs provided: need " + $limit + " have " + $addrs.Count
    }

    return ,$addrs[0 .. ($limit - 1)]
}

################################################################################
#

# Read in any default OVF property values
$props = ReadDefaultProperties $ovfDefaults

# Build our list of authorized keys
$keys = GetKeysFromDir $keyDir

if ($keys.Count -eq 0) {
  Throw "No authorized public keys found in '" + $keyDir + "'"
}

# Add the cloud-config file to our VM properties
$props['guestinfo.coreos.config.data'] = EncodeCloudConfig $cloudConfig $keys
$props['guestinfo.coreos.config.data.encoding'] = 'base64'

$nodeNames = NewNodeNames $nodes
$ips = ,$ipAddrs | ConvertTo-IPAddrs | Select-IPs -limit $nodes

# Load the VMWare snapin
Add-PSSnapin VMware.VimAutomation.Core

# Connect to a Virtual Center server
if (!($global:DefaultVIServers.Count)) {
    if ($vCenterServer) {
      Connect-VIServer $vCenterServer
    }
    else {
      Connect-VIServer
    }
}

#
$ovfConf = Get-OvfConfiguration -Ovf $ovaFile

#
$vmCluster = Get-Cluster $clusterName

$datastore = Get-Datastore |
  Where Name -Like $dsPrefix |
  Sort -Desc FreeSpaceGB |
  Select -First 1

Write "Nodes"
$nodeNames | ft -autosize
Write ""

#
Write "IP Addresses"
$ips | % {$_.IPAddressToString} | ft -autosize
Write ""

Write "OVF Config"
$ovfConf.ToHashTable().GetEnumerator() | Sort Name | ft -autosize

Write "Props"
$props.GetEnumerator() | Sort Name | ft -autosize

# Everything checked out? Get a new cluster ID
#Write "Cluster ID"
#NewClusterID $nodes | ft -autosize
