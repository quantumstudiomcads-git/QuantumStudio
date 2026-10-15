import React from 'react';
import Layout from '@theme/Layout';
import Link from '@docusaurus/Link';
import useBaseUrl from '@docusaurus/useBaseUrl';
import {betaAccessDestination, getAuthSession} from '../lib/auth-client';
import {BetaAccessApplicationPanel} from './BetaApplicationStatus';

type Status = 'READY' | 'PARTIAL' | 'PLANNED' | 'EXTERNAL BACKEND REQUIRED';

function StatusLabel({status}: {status: Status}): React.ReactNode {
  const tone = status === 'READY' ? 'ready' : status === 'PARTIAL' ? 'partial' : status === 'PLANNED' ? 'planned' : 'external';
  return <span className={`qs-status qs-status--${tone}`}>{status}</span>;
}

function Section({title, tint = false, children}: {title: string; tint?: boolean; children: React.ReactNode}): React.ReactNode {
  return <section className={`qs-section${tint ? ' qs-section--tint' : ''}`}><div className="container"><h2>{title}</h2>{children}</div></section>;
}

function Intro({eyebrow, title, description}: {eyebrow: string; title: string; description: string}): React.ReactNode {
  return <section className="qs-intro"><div className="container qs-intro__layout"><span className="qs-kicker">{eyebrow}</span><h1>{title}</h1><p>{description}</p></div></section>;
}

function Page({title, description, eyebrow, children}: {title: string; description: string; eyebrow: string; children: React.ReactNode}): React.ReactNode {
  return <Layout title={title} description={description}><main className="qs-page"><Intro eyebrow={eyebrow} title={title} description={description} />{children}</main></Layout>;
}

function Brand(): React.ReactNode {
  const logo = useBaseUrl('img/brand/quantum-studio-v0.1.svg');
  return <div className="qs-intro__brand"><img className="qs-intro__logo" src={logo} alt="Quantum Studio" /><div className="qs-intro__wordmark">Quantum <span>Studio</span></div></div>;
}

function BetaAccessLink({className, children}: {className?: string; children: React.ReactNode}): React.ReactNode {
  const baseUrl = useBaseUrl('/');
  const loginHref = betaAccessDestination(false, baseUrl);
  const navigate = (event: React.MouseEvent<HTMLAnchorElement>) => {
    event.preventDefault();
    void getAuthSession()
      .then(({authenticated}) => window.location.assign(betaAccessDestination(authenticated, baseUrl)))
      .catch(() => window.location.assign(loginHref));
  };

  return <a className={className} href={loginHref} onClick={navigate}>{children}</a>;
}

function StatusSummary(): React.ReactNode {
  return <div className="qs-table-wrap"><table className="qs-table"><thead><tr><th scope="col">Catalogue status</th><th scope="col">Count</th><th scope="col">Meaning in this technical beta</th></tr></thead><tbody>
    <tr><td><StatusLabel status="READY" /></td><td>29</td><td>Implemented for the documented scope.</td></tr>
    <tr><td><StatusLabel status="PARTIAL" /></td><td>17</td><td>Available with documented limitations or incomplete workflow coverage.</td></tr>
    <tr><td><StatusLabel status="PLANNED" /></td><td>101</td><td>Public scientific intent; not represented as implemented.</td></tr>
    <tr><td><StatusLabel status="EXTERNAL BACKEND REQUIRED" /></td><td>1</td><td>Requires an external backend before completion.</td></tr>
  </tbody></table></div>;
}

export function HomePage(): React.ReactNode {
  return <Layout title="Controlled technical beta" description="Quantum Studio 0.2.0 professor technical preview"><main className="qs-page">
    <section className="qs-intro"><div className="container qs-intro__layout"><Brand /><span className="qs-kicker">Quantum Studio 0.2.0 / controlled technical beta</span><h1>Desktop research software for atomistic systems and electronic-structure workflows.</h1><p>Quantum Studio is a desktop environment for constructing atomistic systems, preparing electronic-structure workflows, and reviewing calculated results. Professor technical-preview access is limited and reviewed manually.</p><div className="qs-actions"><BetaAccessLink className="qs-button qs-button--primary">Request Beta Access</BetaAccessLink><Link className="qs-button" to="/capabilities">Explore Capabilities</Link></div></div></section>
    <Section title="What researchers can do"><div className="qs-columns"><article><h3>Prepare structures and projects</h3><p>Organize projects, construct or import structures, and use supported crystal, slab, supercell, nanotube, heterostructure, and moiré workflows.</p></article><article><h3>Plan calculations explicitly</h3><p>Use public calculation intents with stated readiness rather than assuming every requested calculation is available.</p></article><article><h3>Review calculated results</h3><p>Move from calculation planning to structured result analysis with verification-oriented execution practices.</p></article><article><h3>Evaluate with evidence</h3><p>Inspect platform validation, limitations, and public documentation before deciding whether the beta fits a research workflow.</p></article></div></Section>
    <Section title="Project → Builder → Calculate → Analyze" tint><div className="qs-flow"><article className="qs-flow__step"><span className="qs-flow__number">01</span><h3>Project</h3><p>Organize a research task and its supporting structure data.</p></article><article className="qs-flow__step"><span className="qs-flow__number">02</span><h3>Builder</h3><p>Construct, import, and prepare supported atomistic systems.</p></article><article className="qs-flow__step"><span className="qs-flow__number">03</span><h3>Calculate</h3><p>Choose a documented intent and inspect its readiness boundary.</p></article><article className="qs-flow__step"><span className="qs-flow__number">04</span><h3>Analyze</h3><p>Review results and independently validate scientific conclusions.</p></article></div></Section>
    <Section title="Current validation status"><div className="qs-table-wrap"><table className="qs-table"><thead><tr><th scope="col">Area</th><th scope="col">Current evidence</th><th scope="col">Boundary</th></tr></thead><tbody><tr><td>Windows</td><td>Application build and GUI-only installer lifecycle validated.</td><td>A real production N → N+1 upgrade remains unproven.</td></tr><tr><td>Linux</td><td>Linux x86_64 staging AppImage built and audited in GitHub Actions.</td><td>Staging artifact; not a public production release.</td></tr><tr><td>Updater</td><td>Signed-update infrastructure exists with separate updater and licensing trust domains.</td><td>Production signing has not been activated.</td></tr></tbody></table></div></Section>
    <Section title="Calculation catalogue" tint><p>The public catalogue records 148 calculation intents. A single request may expand into a private dependency graph; its public status is not a blanket scientific-validation claim.</p><StatusSummary /><div className="qs-quiet-links"><Link to="/calculations">View calculation catalogue</Link><Link to="/documentation">Read public documentation</Link></div></Section>
    <Section title="Technical preview and research collaboration"><div className="qs-columns"><article><h3>Controlled access</h3><p>Downloads are available only after manual approval when controlled artifact hosting is configured. The Engine Pack is not included.</p><Link to="/technical-preview">Review technical-preview evidence</Link></article><article><h3>Research collaboration</h3><p>We are seeking scoped professor and research-group evaluation feedback on supported workflows, reproducibility, and usability.</p><Link to="/contact">Discuss research collaboration</Link></article></div></Section>
    <Section title="Transparent beta limitations" tint><div className="qs-note"><strong>Evaluation software, not an unrestricted commercial release.</strong><p>Access is approval-based; temporary licences are not issued automatically. Researchers remain responsible for independently validating scientific results. Legal text remains draft pending counsel review.</p></div></Section>
  </main></Layout>;
}

export function CapabilitiesPage(): React.ReactNode {
  return <Page title="Capabilities" eyebrow="Product scope / controlled beta" description="Implemented, partial, planned, and external-backend-required work are labelled so research groups can assess the beta on its actual evidence.">
    <Section title="Readiness is part of the product surface"><StatusSummary /></Section>
    <Section title="Current workflow scope" tint><dl className="qs-definition-list"><dt>Structure and project preparation</dt><dd>Project management, structure building, structure import, and supported preparation workflows.</dd><dt>Atomistic construction</dt><dd>Crystal, slab, supercell, nanotube, heterostructure, and moiré workflows where supported.</dd><dt>Electronic-property workflows</dt><dd>Calculation planning and documented electronic-property workflow support with explicit readiness boundaries.</dd><dt>Results and analysis</dt><dd>Structured scientific results and result-analysis workflows within the documented beta scope.</dd><dt>Verification and reproducibility</dt><dd>Verification-oriented execution practices and public documentation of status and limitations.</dd><dt>Platform and packaging</dt><dd>Validated Windows packaging/lifecycle evidence and a Linux x86_64 staging AppImage, with production-release boundaries stated separately.</dd></dl></Section>
    <Section title="How to use these labels"><p><StatusLabel status="READY" /> is limited to the documented scope. <StatusLabel status="PARTIAL" /> and <StatusLabel status="PLANNED" /> are not silently promoted to complete capabilities. The catalogue also identifies the one <StatusLabel status="EXTERNAL BACKEND REQUIRED" /> intent.</p><div className="qs-quiet-links"><Link to="/calculations">Inspect calculation readiness</Link><Link to="/technical-preview">Inspect platform evidence</Link></div></Section>
  </Page>;
}

export function CalculationsPage(): React.ReactNode {
  const entries: Array<{name: string; category: string; status: Status; detail: React.ReactNode}> = [
    {name: 'Band structure', category: 'Electronic structure', status: 'READY', detail: <Link to="/docs/calculations/band-structure">Electronic dispersion along an ordered reciprocal-space path</Link>},
    {name: 'Density of states', category: 'Electronic structure', status: 'READY', detail: <Link to="/docs/calculations/dos">Total electronic state density versus energy</Link>},
    {name: 'Charge density', category: 'Real-space analysis', status: 'READY', detail: <Link to="/docs/calculations/charge-density">Selected real-space field workflow</Link>},
    {name: 'Spin texture', category: 'Electronic structure', status: 'PARTIAL', detail: <Link to="/docs/calculations/spin-texture">Documented partial workflow</Link>},
    {name: 'Exchange parameters', category: 'Magnetic properties', status: 'PLANNED', detail: <Link to="/docs/calculations/exchange-parameters">Planned public intent</Link>},
  ];
  return <Page title="Calculation Catalogue" eyebrow="148 public intents / status-aware" description="The public catalogue distinguishes scientific intent from the private execution dependency graph that may be needed to fulfil a request.">
    <Section title="Catalogue summary"><StatusSummary /></Section>
    <Section title="Selected documented references" tint><div className="qs-table-wrap"><table className="qs-table"><thead><tr><th scope="col">Calculation</th><th scope="col">Category</th><th scope="col">Readiness</th><th scope="col">Public reference</th></tr></thead><tbody>{entries.map((entry) => <tr key={entry.name}><td>{entry.name}</td><td>{entry.category}</td><td><StatusLabel status={entry.status} /></td><td>{entry.detail}</td></tr>)}</tbody></table></div></Section>
    <Section title="Reading the catalogue"><div className="qs-note"><strong>Readiness is not a universal scientific-results guarantee.</strong><p>Review the applicable reference and independently validate any scientific result for the material system, parameters, and research question at hand.</p></div></Section>
  </Page>;
}

export function ApplicationsPage(): React.ReactNode {
  return <Page title="Applications" eyebrow="Research-facing use cases" description="Quantum Studio is being evaluated for atomistic and electronic-structure research workflows, with roadmap work stated separately from supported scope.">
    <Section title="Research areas"><article><h3>Electronic structure</h3><p>Band, density-of-states, charge, and related electronic-property workflows are represented by public calculation intents with individual readiness labels.</p><Link to="/calculations">Review the calculation catalogue</Link></article><article><h3>Materials modelling</h3><p>Project organization, structure construction, import, and reproducible calculation planning support research groups preparing documented workflows.</p></article><article><h3>Heterostructures and moiré structures</h3><p>Builder workflows for layered systems are available where the corresponding construction path is supported.</p><Link to="/docs/builder/overview">Read the builder overview</Link></article><article><h3>Vibrational, optical, and device-oriented work</h3><p>These areas include partial, planned, or external-backend-required public intents. They are roadmap context, not a claim of completed workflow coverage.</p></article></Section>
    <Section title="Evaluation scope" tint><div className="qs-note"><strong>Professor technical preview.</strong><p>Use the public readiness labels and beta limitations to select a bounded evaluation. Independent validation remains necessary for all scientific conclusions.</p></div></Section>
  </Page>;
}

export function ResourcesPage(): React.ReactNode {
  return <Page title="Resources" eyebrow="Public learning materials" description="Public resources cover capabilities, selected tutorials, verification boundaries, and project format without exposing the subscriber manual.">
    <Section title="Public resources"><dl className="qs-definition-list"><dt><Link to="/documentation">Documentation overview</Link></dt><dd>High-level workflow material, public references, and the documentation boundary.</dd><dt><Link to="/docs/tutorials/silicon-scf">Silicon SCF tutorial</Link></dt><dd>A selected public tutorial.</dd><dt><Link to="/docs/reference/project-format">Project format</Link></dt><dd>Public reference material for the project format.</dd><dt><Link to="/technical-preview">Technical preview</Link></dt><dd>Packaging evidence, staging status, and controlled-beta limitations.</dd></dl></Section>
  </Page>;
}

export function DocumentationPage(): React.ReactNode {
  return <Page title="Documentation Overview" eyebrow="Public documentation" description="High-level guidance, selected tutorials, capability explanations, and public verification summaries are available without exposing the complete subscriber manual.">
    <Section title="Available public documentation"><div className="qs-columns"><article><h3><Link to="/docs/getting-started/installation">Getting started</Link></h3><p>Installation and first-project orientation.</p></article><article><h3><Link to="/docs/builder/overview">Builder overview</Link></h3><p>Structure-building concepts and supported workflows.</p></article><article><h3><Link to="/calculations">Calculation references</Link></h3><p>Selected public definitions and readiness context.</p></article><article><h3><Link to="/docs/troubleshooting">Troubleshooting</Link></h3><p>The single canonical troubleshooting route.</p></article></div></Section>
    <Section title="Subscriber manual" tint><div className="qs-note"><strong>Controlled access.</strong><p>The complete paid/subscriber manual is not included in this public build. Subscriber authentication and deployment are not yet operational, so the site does not simulate access.</p></div></Section>
  </Page>;
}

export function TechnicalPreviewPage(): React.ReactNode {
  return <Page title="Technical Preview" eyebrow="Release engineering / controlled beta" description="Technical-preview packages are available only through approved beta access when controlled artifact hosting has been configured.">
    <Section title="0.2.0 release evidence"><div className="qs-table-wrap"><table className="qs-table"><thead><tr><th scope="col">Item</th><th scope="col">Status</th><th scope="col">Evidence or boundary</th></tr></thead><tbody><tr><td>Channel</td><td>Controlled technical beta</td><td>Access remains approval-based.</td></tr><tr><td>Windows</td><td>Validated packaging</td><td>Application build and GUI-only installer lifecycle validated; Engine Pack not included; production N → N+1 upgrade not yet proven.</td></tr><tr><td>Linux x86_64</td><td>Staging AppImage</td><td>Genuine staging build from <code>a9b7a078ad30fc744fd2aba3ef384d01e2c72a82</code>; not a public production release.</td></tr><tr><td>Linux checksum</td><td>SHA-256</td><td><code>B31AE6E5A62876B4CD8AE0E3C37F5C9940D7776DAEE3888FB884D8BD4801C2FB</code></td></tr><tr><td>Updater</td><td>Signing-ready infrastructure</td><td>Separate update and licence trust domains exist; production signing has not been activated.</td></tr><tr><td>Engine Pack</td><td>Not included</td><td>No scientific-engine binaries are bundled or represented as redistributed.</td></tr></tbody></table></div></Section>
    <Section title="Access and known limitations" tint><div className="qs-note"><strong>No public download is presented before controlled hosting is ready.</strong><p>Request beta access for administrator-reviewed eligibility. A successful application does not issue a licence or create a public download entitlement.</p></div><div className="qs-actions"><BetaAccessLink className="qs-button qs-button--primary">Request Beta Access</BetaAccessLink></div></Section>
  </Page>;
}

export function BetaAccessPage(): React.ReactNode {
  return <Page title="Beta Access" eyebrow="Professor technical preview" description="Apply for limited, administrator-reviewed access to Quantum Studio 0.2.0. Approval is manual and any licence is temporary.">
    <Section title="Before you apply"><ul className="qs-list"><li>Engine Pack binaries are not included.</li><li>Scientific results must be independently validated by the research group.</li><li>Information is collected only to administer beta review and temporary licences.</li><li>Approval is manual; a submitted application does not issue a licence.</li></ul></Section>
    <Section title="Application" tint><BetaAccessApplicationPanel /></Section>
  </Page>;
}

export function LicencePage(): React.ReactNode {
  return <Page title="Temporary Licence Information" eyebrow="Approval-based access" description="Temporary beta licences are not issued automatically and this website does not sign or deliver licences.">
    <Section title="Licence boundary"><dl className="qs-definition-list"><dt>Manual review</dt><dd>An operator reviews a submitted beta application before approval.</dd><dt>Temporary and scoped</dt><dd>An approved beta licence may define expiry, platform scope, and feature scope.</dd><dt>Revocable</dt><dd>Access may expire or be revoked under the beta terms.</dd></dl></Section>
    <Section title="Current implementation boundary" tint><div className="qs-note"><strong>No browser endpoint can issue a licence.</strong><p>Private registration storage and operator-controlled administration are deployment requirements. Licence issuance remains a separate controlled operation.</p></div></Section>
  </Page>;
}

export function PrivacyPage(): React.ReactNode {
  return <Page title="Privacy Notice" eyebrow="Draft — pending legal review" description="Version 0.1 / effective 20 September 2026. This draft describes the intended privacy-conscious beta process and is not final legal advice.">
    <Section title="Information and purpose"><ul className="qs-list"><li>The beta form requests name, email, institution, country, intended use, operating system, optional academic role, optional evaluation description, and consent choices.</li><li>These fields support manual beta review, temporary-licence administration, and optional communications only where separately consented.</li><li>The form does not request passwords, payment information, government identification, raw hardware serial numbers, project files, scientific datasets, calculation inputs/results, or unrestricted telemetry.</li></ul></Section>
    <Section title="Storage, retention, and requests" tint><p>When deployed, applications are held in a private Cloudflare D1 database and reviewed by authorized operators. The local preview is not a live collection service. The proposed retention period is 90 days for rejected applications and the beta period plus 12 months for approved or licence-related records, pending final legal review. Export and deletion/anonymization requests may be made through the approved contact channel. Personal information is not sold.</p><p>Contact placeholder: <code>beta-access@quantumstudio.example</code>.</p></Section>
  </Page>;
}

export function TermsPage(): React.ReactNode {
  return <Page title="Beta Terms" eyebrow="Draft — pending legal review" description="These draft terms describe the intended controlled technical beta and require counsel review before use.">
    <Section title="Evaluation terms"><ul className="qs-list"><li>Access is evaluation-only, manually reviewed, temporary, and revocable; application acceptance does not itself issue a licence.</li><li>Do not redistribute software or share licence files.</li><li>The software is experimental; no scientific-results guarantee is made, and users must independently validate results.</li><li>The Engine Pack is not included. Third-party software remains governed by its own licences.</li><li>Access may expire, terminate, or be revoked. Confidentiality applies only where separately agreed.</li><li>Governing law and final notices remain placeholders for counsel review.</li></ul></Section>
  </Page>;
}

export function ContactPage(): React.ReactNode {
  return <Page title="Research Collaboration" eyebrow="Contact / collaboration" description="Quantum Studio is seeking carefully scoped professor and research-group feedback during the controlled technical beta.">
    <Section title="A focused evaluation conversation"><div className="qs-columns"><article><h3>Research workflow</h3><p>Describe the atomistic or electronic-structure workflow you intend to evaluate.</p></article><article><h3>Platform needs</h3><p>Indicate whether the evaluation is planned for Windows, Linux, or both.</p></article><article><h3>Validation feedback</h3><p>Share reproducibility and usability observations after approval through the controlled beta channel.</p></article></div></Section>
    <Section title="Contact" tint><div className="qs-note"><strong>Controlled beta contact.</strong><p>Placeholder: <code>beta-access@quantumstudio.example</code>. Replace this with an approved, monitored contact method before deployment.</p></div><div className="qs-actions"><BetaAccessLink className="qs-button qs-button--primary">Request Beta Access</BetaAccessLink></div></Section>
  </Page>;
}
