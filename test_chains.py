"""Test the recon chain end-to-end."""
import json
import logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")

from chains.recon import ReconChain


def main():
    print("=" * 70)
    print("RECON CHAIN TEST")
    print("=" * 70)

    chain = ReconChain()

    print()
    print("Tool availability:")
    print(f"  subfinder: {chain.subfinder.available()}")
    print(f"  httpx:     {chain.httpx.available()}")
    print(f"  nuclei:    {chain.nuclei.available()}")
    print()

    domain = "example.com"
    print(f"Running recon on: {domain}")
    print("-" * 70)

    result = chain.run(domain)

    print()
    print("RESULT:")
    print(f"  Success: {result.success}")
    if result.error:
        print(f"  Error: {result.error}")
    print(f"  Subdomains found: {len(result.subdomains)}")
    print(f"  Live hosts:       {len(result.live_hosts)}")
    print(f"  Findings:         {len(result.findings)}")
    print(f"  Total duration:   {result.total_duration_ms}ms")
    print()
    print("STEPS:")
    for step in result.steps:
        print(f"  {step}")

    print()
    print("SAMPLE SUBS (first 5):")
    for s in result.subdomains[:5]:
        print(f"  - {s}")

    print()
    print("SAMPLE LIVE HOSTS (first 3):")
    for h in result.live_hosts[:3]:
        print(f"  - {h.get('url')} [{h.get('status_code')}] {h.get('title')}")

    print()
    print("SAMPLE FINDINGS (first 5):")
    for f in result.findings[:5]:
        print(f"  - [{f.get('severity')}] {f.get('name')} @ {f.get('target')}")

    print()
    print("JSON output size:", len(json.dumps(result.to_dict())), "chars")


if __name__ == "__main__":
    main()