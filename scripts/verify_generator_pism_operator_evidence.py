from __future__ import annotations
import argparse, json
from hashlib import sha256
from pathlib import Path

EXPECTED=("final.docx","final.pdf","document.json","validation.json","sources.json",
          "evidence-map.json","argument-map.json","audit.json","release.json","manifest.json")

def digest(data: bytes)->str: return sha256(data).hexdigest()

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--evidence",required=True); p.add_argument("--package-dir",required=True)
    p.add_argument("--expected-sha",required=True); p.add_argument("--output",required=True)
    a=p.parse_args()
    ep=Path(a.evidence); pd=Path(a.package_dir); eb=ep.read_bytes(); e=json.loads(eb)
    assert e["contract"]=="urn:lukart:work:GeneratorPismOperatorE2EEvidence:1.0.0"
    assert e["result"]=="PASS" and e["tested_sha"]==a.expected_sha and len(a.expected_sha)==40
    assert e["synthetic_only"] is True and e["human_actor_kind"]=="HUMAN"
    assert e["legal_type_admission"]=="HUMAN_REQUIRED" and e["release_eligibility"]=="FINAL"
    assert e["package_member_count"]==10
    assert tuple(x["name"] for x in e["package_members"])==EXPECTED
    verified=[]
    for item in e["package_members"]:
        data=(pd/item["name"]).read_bytes()
        assert len(data)==item["byte_length"] and digest(data)==item["content_hash"], item["name"]
        verified.append({"name":item["name"],"content_hash":item["content_hash"],"byte_length":item["byte_length"]})
    docx=(pd/"final.docx").read_bytes(); pdf=(pd/"final.pdf").read_bytes()
    assert docx.startswith(b"PK") and pdf.startswith(b"%PDF")
    assert digest(docx)==e["direct_artifacts"]["final.docx"]["content_hash"]
    assert digest(pdf)==e["direct_artifacts"]["final.pdf"]["content_hash"]
    manifest=json.loads((pd/"manifest.json").read_text(encoding="utf-8"))
    assert len(manifest["members"])==9 and tuple(x["name"] for x in manifest["members"])==EXPECTED[:-1]
    release=json.loads((pd/"release.json").read_text(encoding="utf-8")); assert "FINAL" in json.dumps(release)
    report={"contract":"urn:lukart:work:GeneratorPismIndependentVerifier:1.0.0","result":"PASS",
            "tested_sha":a.expected_sha,"evidence_hash":digest(eb),"verified_members":verified,
            "checks":["exact-sha","synthetic-only","human-boundary","final-release","ten-member-package",
                      "member-byte-hashes","docx-magic","pdf-magic","manifest-nine-member-binding"]}
    out=Path(a.output); out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({"result":"PASS","tested_sha":a.expected_sha,"output":str(out)}))
if __name__=="__main__": main()
