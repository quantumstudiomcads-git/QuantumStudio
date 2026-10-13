import type {SidebarsConfig} from '@docusaurus/plugin-content-docs';

const sidebars: SidebarsConfig = {
  docsSidebar: [
    'intro',
    {type: 'category', label: 'Getting Started', items: ['getting-started/installation']},
    {type: 'category', label: 'Builder', items: ['builder/overview']},
    {type: 'category', label: 'Calculate', items: ['calculate/overview']},
    {type: 'category', label: 'Analyze', items: ['analyze/overview']},
    {type: 'category', label: 'Tutorials', items: ['tutorials/silicon-scf']},
    {type: 'category', label: 'Concepts', items: ['concepts/dft']},
    {type: 'category', label: 'Reference', items: ['reference/project-format', 'reference/open-source']},
    {type: 'category', label: 'Selected calculation references', items: [
      'calculations/band-structure', 'calculations/band-gap', 'calculations/effective-mass', 'calculations/dos', 'calculations/pdos',
      'calculations/charge-density', 'calculations/spin-density', 'calculations/elf', 'calculations/electrostatic-potential',
      'calculations/band-decomposed-charge', 'calculations/fermi-surface', 'calculations/work-function', 'calculations/bader-charge',
      'calculations/charge-transfer', 'calculations/lowdin-population', 'calculations/orbital-character', 'calculations/magnetic-moments',
      'calculations/dft-plus-u', 'calculations/hubbard-u', 'calculations/hybrid-functionals', 'calculations/spin-texture',
      'calculations/soc-pdos', 'calculations/exchange-parameters',
    ]},
    'troubleshooting/index',
  ],
};

export default sidebars;
