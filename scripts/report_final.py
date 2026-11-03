"""Generate owner-facing methods and quality reports from measured receipts."""
import argparse
import json
from pathlib import Path
from collections import Counter
from analytics_final import measured_report


def read(path,default=None):
    return json.loads(path.read_text()) if path.exists() else default


def block(value):
    return '```json\n'+json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2)+'\n```\n'


def generate(private,public,docs):
    counts=read(public/'counts.json');manifest=read(public/'manifest.json')
    public_coverage=read(public/'quality.json',{}).get('coverage',{})
    report=measured_report(private);queries=read(private/'query_log.json',[])
    tiers=read(private/'TIER-REPORT.json');dedup=read(private/'DEDUPLICATION.json')
    retry=read(private/'gap_retries.json',[]);s2=read(private/'s2_fix_report.json',{})
    vectors=read(private/'vector_manifest.json',{});matrix=read(private/'matrix.private.json',{})
    analytics=read(public/'analytics.json',{});clusters=analytics.get('clusters',[])
    docs.mkdir(parents=True,exist_ok=True)
    # Preserve earlier-stage narrative without leaving obsolete claims in the
    # current methods/limitations documents.
    history=docs/'history';history.mkdir(exist_ok=True)
    for name in ['METHODS.md','LIMITATIONS.md']:
        target=history/('checkpoint-2-'+name)
        if not target.exists() and (docs/name).exists():target.write_bytes((docs/name).read_bytes())
    methods='''# Methods — final snapshot

This report describes the final three-tier census. The earlier embedding-threshold checkpoint is historical, not the final inclusion rule.

Processing, embeddings, projection, clustering and extraction run on the private server. Raw responses, analysis abstracts, model responses and vectors stay outside this repository. Credentials come from process environment variables. Public outputs contain metadata, permitted abstract text and permitted evidence quotes; no full texts are copied.

Seeds A–E supplied the original citation/reference expansion; group F remains theory anchors. Both APIs were searched with the English title/abstract queries below, from 2023 to the printed cutoff. Semantic Scholar uses relevance search, 100 records per page and a 1,000-result cap per query. Reported totals and acquired occurrences differ from unique papers. Failed requests and capped searches remain explicit. The parent gaps received their specified one-time retry. Interrupted final keyword searches received one slower recovery pass, reusing successful cached pages.

Deduplication uses DOI, arXiv ID, then normalized title plus first author and year, with conflict checks. All source identifiers survive a merge. First-public arXiv dates and venue years remain separate; missing dates are not invented. The timeline uses known first-public dates.

The score-blind model sees title and available abstract, never the embedding score. CORE concerns persistent agent memory as the main contribution; ADJACENT concerns a substantive memory component or a direct method/theory anchor. Other candidates are EXCLUDE. Owner-specified seed tiers override the proposal, while the proposal and actual model provenance remain recorded. Optional scope pointers are validated separately from required tier/rationale fields. Estimated screening precision is pending the owner's stratified labels.

Jina document vectors use the pinned model, dimension and passage task below; live search uses its query task. Content hashes reuse unchanged vectors. Stored vectors are normalized float16. Public semantic coordinates do not establish citation or support.

UMAP and HDBSCAN use fixed random seeds and recorded parameters. Cluster names are model interpretations of top terms and central source titles, not a validated taxonomy. Citation, semantic, co-citation and bibliographic-coupling relations remain distinct. Total citation display uses the maximum available source count, not a sum across providers; in-corpus counts use resolved directed edges.

Every CORE paper has a capability row. Positive or partial cells require an exact enclosing abstract sentence and verified character offsets. Missing statements, unavailable abstracts and validation failures remain unknown, with distinct reasons. A source license must permit the exact selected abstract before its text or extracted quote is published. A ten-percent CORE sample is extracted with a second prompt wording; agreement measures repeatability of model extraction, not human accuracy. Benchmark fields retain exact supporting locations.

Live chat retrieves private analysis abstracts, checks exact cited passages and runs a separate support check. It retains at most the last four supplied messages as context. Unsupported or unreachable-model cases refuse explicitly. Questions are not written to the research response cache. Local reading notes and verification badges remain in the browser. Positioning and project rankings are retrieval aids; the configured project abstract is a labeled placeholder.

## Generated census

'''+block(counts)+'\n## Tier provenance and denominator\n\n'+block(tiers)+'\n## Acquisition and deduplication\n\n'+block(dedup)+'\n## Query log\n\n'+block(queries)+'\n## Semantic Scholar recovery\n\n'+block(s2)+'\n## Embedding parameters and coverage\n\n'+block({'parameters':vectors.get('parameters'),'rows':len(vectors.get('documents',[])),'representation_counts':dict(Counter(r.get('representation') for r in vectors.get('documents',[]))),'new_vectors':vectors.get('new_vectors'),'reused_vectors':vectors.get('reused_vectors')})+'\n## Analytics and extraction measurements\n\n'+block(report)
    methods+='\n## Primary-source provenance verification\n\n'+block(read(private/'PROVENANCE-VERIFICATION.json',{'status':'not run'}))
    methods+='\n## Public text coverage\n\nWhole public abstract or evidence text fields containing an IPv4 address are withheld for privacy. The original private source and scientific inputs are unchanged. Privacy withholding is separate from content-license withholding.\n\n'+block(public_coverage)
    (docs/'METHODS.md').write_text(methods)
    limitations='''# Coverage and use limitations

This is a dated, acquired research snapshot. It is not an exhaustive survey, a validated taxonomy, a novelty certificate or a human-verified capability database.

- API indexing gaps, missing seed lookups, incomplete citation acquisition, search caps and transient errors limit coverage. An unsuccessful lookup does not show that a work does not exist. Stored totals reflect their own retrieval times.
- English queries and supplied seeds bias terminology, language and research direction. arXiv-only records and separate published versions can be incompletely linked. Suspected identity conflicts remain visible for owner review.
- Final inclusion uses model tiers, not the earlier centroid threshold. Estimated precision is **pending owner labels**. The historical 60-item agreement is not a current human precision estimate. The 100-item owner sample is stratified and needs weighting for a corpus-level estimate.
- Abstract availability is different from permission to display it. Title-only records offer less evidence. API abstract fields can include extracted figure or page text; they have not all received manual boundary checks. No full texts were acquired for this final analysis. Open-access links are availability metadata, not evidence that the linked paper was read.
- The timeline omits unknown first-public dates rather than inventing dates. Venue years can differ from arXiv v1 years. Citation counts vary across providers and retrieval times.
- Similarity is not citation, evidence or support. Projection distances are approximate. Clusters and model-written labels are exploratory. Graph relations are computed only over the acquired corpus, with recorded edge-selection parameters.
- Matrix cells are model extractions from available abstracts. A quoted sentence can still be misinterpreted. Not stated means unknown; it never establishes absence. Validation failures are separately reported. Second-prompt agreement, often using the same model, is not human validation.
- License-withheld quotes cannot be checked inside this interface. Follow the original source. A verified badge records the owner's local check of this snapshot and exact cell, not a server certification.
- The project abstract is a labeled placeholder. Positioning results are corpus-limited retrieval leads and never establish novelty or priority. Static positive coverage requires an exact full supporting-quote match; nearest-neighbour retrieval alone is insufficient.
- Live semantic queries and chat require the local gateway and reachable providers. Lexical exploration and static evidence remain usable when they are offline. Questions are not stored by this application or its private router; upstream services have their own policies.
- Citation contexts, benchmark licenses, code release status and other resource fields may be unstated or unacquired. A reported code URL alone does not verify that a release is available.

## Licensing conclusion

OpenAlex documents its dataset as CC0, but its work-object documentation separately explains legal constraints on plaintext abstracts. Metadata access therefore does not authorize blanket abstract republication. Semantic Scholar's API license permits compatible products to access and display data subject to its license and underlying content licenses, and requires attribution. This atlas credits OpenAlex and Semantic Scholar. A later scientific publication using these results must cite the Semantic Scholar Open Data Platform.

The implementation defaults to withholding text. It allows the configured explicit CC0/CC-BY/CC-BY-SA license variants only when a licensed source observation contains exactly the selected abstract. Unknown and incompatible permissions remain withheld. An open PDF link alone does not authorize copying its text. The raw policy responses remain private with their retrieval timestamps and hashes; they were originally retrieved on 2026-11-01. The official OpenAlex pages were re-opened during final verification; the cached successful Semantic Scholar license response was re-opened after its current documentation fetch returned 403. No access control was bypassed.

Sources: [OpenAlex licensing FAQ](https://github.com/ourresearch/openalex-docs/blob/main/additional-help/faq.md), [OpenAlex abstract field](https://github.com/ourresearch/openalex-docs/blob/main/api-entities/works/work-object/README.md#abstract_inverted_index), [Semantic Scholar API license](https://www.semanticscholar.org/product/api/license).

## Generated coverage measurements

'''+block({'snapshot':manifest.get('snapshot'),'counts':counts,'parent_gap_retry_status':dict(Counter(str(r.get('status')) for r in retry)),'matrix_coverage':matrix.get('coverage'),'self_check':{k:v for k,v in matrix.get('self_check',{}).items() if k not in ('second_extraction','differences')},'quality_summary':matrix.get('method',{}).get('quality_summary')})
    limitations+='\n## Privacy withholding\n\nWhole public abstract or evidence text fields containing an IPv4 address are withheld, with a privacy-specific reason. This does not change the private source, corpus tiers or embeddings. Permission withholding is reported separately.\n\n'+block(public_coverage)
    (docs/'LIMITATIONS.md').write_text(limitations)
    quality='# Data quality — final snapshot\n\nThe public data-quality workspace contains metadata-only exclusions and unresolved acquisition/identity diagnostics. Owner labels remain pending. Raw API responses and private analysis text are not part of this report.\n\n'+block({'counts':counts,'deduplication':dedup,'parent_gap_retry_status':dict(Counter(str(r.get('status')) for r in retry)),'s2_recovery':s2,'deferred':{k:v for k,v in read(private/'deferred_resolution.json',{}).items() if k!='resolved'},'measurements':report})
    (docs/'DATA-QUALITY.md').write_text(quality)
    cluster_lines=['# Exploratory topic clusters','','Labels are model interpretations, supported by the central paper titles stored in the snapshot. Noise is not a topic cluster.','','| Cluster | Label | Papers |','| --- | --- | ---: |']
    for cluster in clusters:
        cluster_lines.append('| '+str(cluster.get('id',cluster.get('cluster_id')))+' | '+str(cluster.get('label','')).replace('|','\\|')+' | '+str(cluster.get('size',cluster.get('count','unknown')))+' |')
    (docs/'CLUSTERS.md').write_text('\n'.join(cluster_lines)+'\n')
    return {'documents':['METHODS.md','LIMITATIONS.md','DATA-QUALITY.md','CLUSTERS.md'],'snapshot':manifest.get('snapshot',{}).get('id'),'clusters':len(clusters)}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--private',type=Path,required=True);p.add_argument('--public',type=Path,required=True);p.add_argument('--docs',type=Path,required=True);a=p.parse_args();print(json.dumps(generate(a.private,a.public,a.docs),sort_keys=True))
