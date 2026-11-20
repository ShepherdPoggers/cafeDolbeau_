#!/usr/bin/env python3
"""Refuser tout retrait ou remplacement EC2/EBS dans un plan Terraform JSON."""
import json
import sys


def check(plan):
    for resource in plan.get("resource_changes", []):
        if resource["type"] in {"aws_instance", "aws_ebs_volume", "aws_volume_attachment"}:
            if "delete" in resource["change"]["actions"]:
                raise ValueError(f"Suppression/remplacement refusé : {resource['address']}")
        if resource["type"] == "aws_instance":
            change = resource["change"]
            before, after = change.get("before"), change.get("after")
            if before and after and before.get("root_block_device") != after.get("root_block_device"):
                raise ValueError(f"Modification du disque racine refusée : {resource['address']}")


if __name__ == "__main__":
    try:
        check(json.load(sys.stdin))
    except ValueError as exc:
        sys.exit(str(exc))
