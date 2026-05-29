"""Security configuration generators for external monitoring tools."""

import json


def generate_auditd_rules(data_dir: str = "/data") -> str:
    """Generate auditd rules for file integrity monitoring.

    Args:
        data_dir: The data directory to monitor.

    Returns:
        Auditd rules content as a string.
    """
    return f"""# EDMS File Integrity Monitoring Rules
-w {data_dir} -p wa -k dms_data
-w {data_dir} -p a -k dms_data_access
# Monitor for mass renames
-a always,exit -F arch=b64 -S rename -S renameat -F dir={data_dir} -k dms_rename
# Monitor for mass deletes
-a always,exit -F arch=b64 -S unlink -S unlinkat -F dir={data_dir} -k dms_delete
"""


def generate_falco_rules() -> str:
    """Generate Falco rules for process monitoring.

    Returns:
        Falco rules content as a YAML string.
    """
    return """- rule: Unexpected Process from EDMS Worker
  desc: Detect unexpected child processes spawned by DMS workers
  condition: spawned_process and proc.pname in (uvicorn, python, gunicorn) and not proc.name in (python, uvicorn, gunicorn, tesseract, gs, pdftoppm)
  output: "Unexpected process spawned by EDMS worker (user=%user.name command=%proc.cmdline parent=%proc.pname)"
  priority: WARNING
  tags: [edms, process]
"""


def generate_suricata_rules() -> str:
    """Generate Suricata rules for network monitoring.

    Returns:
        Suricata rules content as a string.
    """
    return """# EDMS Network Monitoring Rules
alert tcp $HOME_NET any -> $EXTERNAL_NET any (msg:"EDMS - Possible C2 beacon detected"; flow:to_server,established; content:"POST"; http_method; threshold:type both, track by_src, count 10, seconds 60; sid:1000001; rev:1;)
alert dns $HOME_NET any -> any any (msg:"EDMS - Suspicious DNS query from DMS host"; dns_query; content:".onion"; sid:1000002; rev:1;)
"""


def generate_kms_audit_config() -> str:
    """Generate KMS audit logging configuration.

    Returns:
        JSON config for KMS audit logging rules.
    """
    config = {
        "kms_audit": {
            "enabled": True,
            "log_all_operations": True,
            "alert_rules": [
                {
                    "name": "high_unwrap_rate",
                    "description": "Alert when unwrap_key exceeds 10 calls per minute from a single IP",
                    "condition": "unwrap_key_count > 10 per minute per source_ip",
                    "severity": "high",
                    "action": "block_and_alert",
                },
                {
                    "name": "off_hours_access",
                    "description": "Alert on KMS operations outside business hours",
                    "condition": "operation_time not in business_hours",
                    "severity": "medium",
                    "action": "alert",
                },
            ],
            "retention_days": 90,
            "output_format": "json",
        }
    }
    return json.dumps(config, indent=2)
