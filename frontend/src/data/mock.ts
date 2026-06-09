import type { Target, ValidationTarget, RepurposingDrug, Molecule, BiologicsSeq, MpoMolecule, MDTimepoint } from '../types';

export const MOCK_TARGETS: Target[] = [
  { rank: 1, symbol: 'KRAS', mutation: 'G12D', puScore: 0.984, gtexExpr: 'High', confidence: 94, shap: [{ feature: 'DepMap Essentiality', value: 0.34 }, { feature: 'TCGA Mutation Freq', value: 0.28 }, { feature: 'AlphaMissense', value: 0.19 }, { feature: 'GTEx Normal Expr', value: -0.12 }, { feature: 'STRING Degree', value: 0.09 }] },
  { rank: 2, symbol: 'TGFB1', puScore: 0.912, gtexExpr: 'Med', confidence: 88, shap: [{ feature: 'DepMap Essentiality', value: 0.22 }, { feature: 'TCGA Mutation Freq', value: 0.18 }, { feature: 'AlphaMissense', value: 0.15 }, { feature: 'GTEx Normal Expr', value: -0.08 }, { feature: 'STRING Degree', value: 0.11 }] },
  { rank: 3, symbol: 'EGFR', puScore: 0.875, gtexExpr: 'V.High', confidence: 72, warning: true, shap: [{ feature: 'DepMap Essentiality', value: 0.31 }, { feature: 'TCGA Mutation Freq', value: 0.24 }, { feature: 'AlphaMissense', value: 0.12 }, { feature: 'GTEx Normal Expr', value: -0.29 }, { feature: 'STRING Degree', value: 0.07 }] },
  { rank: 4, symbol: 'TP53', puScore: 0.861, gtexExpr: 'Med', confidence: 85, shap: [{ feature: 'DepMap Essentiality', value: 0.28 }, { feature: 'TCGA Mutation Freq', value: 0.33 }, { feature: 'AlphaMissense', value: 0.17 }, { feature: 'GTEx Normal Expr', value: -0.06 }, { feature: 'STRING Degree', value: 0.08 }] },
  { rank: 5, symbol: 'CDKN2A', puScore: 0.834, gtexExpr: 'Low', confidence: 81, shap: [{ feature: 'DepMap Essentiality', value: 0.19 }, { feature: 'TCGA Mutation Freq', value: 0.21 }, { feature: 'AlphaMissense', value: 0.10 }, { feature: 'GTEx Normal Expr', value: -0.04 }, { feature: 'STRING Degree', value: 0.14 }] },
  { rank: 6, symbol: 'SMAD4', puScore: 0.791, gtexExpr: 'Low', confidence: 76, shap: [{ feature: 'DepMap Essentiality', value: 0.14 }, { feature: 'TCGA Mutation Freq', value: 0.16 }, { feature: 'AlphaMissense', value: 0.09 }, { feature: 'GTEx Normal Expr', value: -0.05 }, { feature: 'STRING Degree', value: 0.06 }] },
];

export const MOCK_VALIDATION: ValidationTarget[] = [
  { id: 'KRAS-G12D', name: 'KRAS G12D Mutant', smiles: 'C1=CC(=CC=C1...', validationScore: 0.942, pocketScore: 88.5, plddt: 94.12, status: 'Validated' },
  { id: 'TP53-MUT-21', name: 'Tumor Protein P53', smiles: 'CC1=CC=C(C=C1...', validationScore: 0.887, pocketScore: 91.2, plddt: 92.05, status: 'Processing' },
  { id: 'TGFB1-AC', name: 'TGF Beta 1 Active', smiles: 'O=C(N)C1=CC...', validationScore: 0.841, pocketScore: 79.4, plddt: 89.31, status: 'Validated' },
  { id: 'EGFR-T790M', name: 'Kinase Domain Mutation', smiles: 'N#CC1=C(N=C...', validationScore: 0.412, pocketScore: 34.1, plddt: 42.18, status: 'Insignificant' },
  { id: 'CDKN2A-WT', name: 'Cyclin Dep Kinase Inh', smiles: 'C1CC1NC(=O)...', validationScore: 0.799, pocketScore: 72.6, plddt: 87.44, status: 'Validated' },
];

export const MOCK_REPURPOSING: RepurposingDrug[] = [
  { name: 'Sotorasib', target: 'KRAS G12C', indication: 'NSCLC → Pancreatic', overallScore: 0.89, narrative: 'AMG-510 (Sotorasib) covalently targets KRAS G12C. Structural similarity between G12C and G12D binding pockets supports repurposing hypothesis. Three ongoing Phase I/II trials in pancreatic cohorts show promising early PK/PD data.', radar: [{ axis: 'Selectivity', value: 88 }, { axis: 'Toxicity', value: 72 }, { axis: 'BBB', value: 45 }, { axis: 'Solubility', value: 81 }, { axis: 'hERG', value: 78 }, { axis: 'Bioavail', value: 91 }] },
  { name: 'Erlotinib', target: 'EGFR WT', indication: 'NSCLC → Pancreatic', overallScore: 0.74, narrative: 'EGFR TKI with established safety profile. Limited efficacy in unselected pancreatic cohorts historically, but recent biomarker-selected subgroups show 18% ORR. Low-risk repurposing candidate.', radar: [{ axis: 'Selectivity', value: 65 }, { axis: 'Toxicity', value: 68 }, { axis: 'BBB', value: 52 }, { axis: 'Solubility', value: 74 }, { axis: 'hERG', value: 82 }, { axis: 'Bioavail', value: 85 }] },
  { name: 'Trametinib', target: 'MEK1/2', indication: 'Melanoma → Pancreatic', overallScore: 0.71, narrative: 'MEK1/2 inhibitor downstream of KRAS. Combination with CDK4/6 inhibitors has shown synergy in PDAC PDX models. Repurposing rationale strong for KRAS-mutated tumors.', radar: [{ axis: 'Selectivity', value: 79 }, { axis: 'Toxicity', value: 61 }, { axis: 'BBB', value: 38 }, { axis: 'Solubility', value: 69 }, { axis: 'hERG', value: 75 }, { axis: 'Bioavail', value: 77 }] },
];

export const MOCK_MOLECULES: Molecule[] = [
  { id: 'MOL-001', smiles: 'CC1=C(C=CC(=C1)F)NC(=O)C2=CC=C(C=C2)CN3CCNCC3', qed: 0.812, sa: 2.41, mw: 372.4, logP: 2.8, lipinski: true, dockScore: -9.4, method: 'REINVENT4' },
  { id: 'MOL-002', smiles: 'C1CN(CCN1)C2=NC(=NC(=N2)N)SC3=CC=CC=C3', qed: 0.741, sa: 2.89, mw: 341.2, logP: 1.9, lipinski: true, dockScore: -8.9, method: 'REINVENT4' },
  { id: 'MOL-003', smiles: 'COC1=CC=C(C=C1)C2=NN=C(O2)NC(=O)C3=CC=NC=C3', qed: 0.698, sa: 3.12, mw: 324.3, logP: 2.2, lipinski: true, dockScore: -8.4, method: 'BRICS' },
  { id: 'MOL-004', smiles: 'CC(C)(C)NC(=O)C1=CC=C(C=C1)OCC2=CC=CC=C2F', qed: 0.654, sa: 2.67, mw: 345.4, logP: 3.4, lipinski: true, dockScore: -8.1, method: 'BRICS' },
  { id: 'MOL-005', smiles: 'C1=CC(=CN=C1)NC2=NC(=CS2)C3=CC=C(C=C3)Cl', qed: 0.631, sa: 3.44, mw: 307.8, logP: 3.1, lipinski: true, dockScore: -7.8, method: 'REINVENT4' },
  { id: 'MOL-006', smiles: 'CC1=CC(=NO1)NC(=O)C2=CSC(=N2)NC3=CC=CC=C3', qed: 0.589, sa: 3.78, mw: 318.4, logP: 2.7, lipinski: true, dockScore: -7.6, method: 'BRICS' },
];

export const MOCK_BIOLOGICS: BiologicsSeq[] = [
  { id: 'PEP-001', sequence: 'MKTAYIAKQRQISFVKSHFSRQ', bindingScore: 0.91, hotspots: [3, 7, 11, 15, 18] },
  { id: 'PEP-002', sequence: 'ACDEFGHIKLMNPQRSTVWY', bindingScore: 0.84, hotspots: [2, 6, 10, 14] },
  { id: 'PEP-003', sequence: 'GRAFSKVFKHGLLGFYATRQ', bindingScore: 0.77, hotspots: [1, 5, 9, 13, 17] },
  { id: 'PEP-004', sequence: 'WQEFLDAIRQKRMEVQFLSP', bindingScore: 0.72, hotspots: [4, 8, 12] },
];

export const MOCK_MPO: MpoMolecule[] = [
  { id: 'MOL-001', smiles: 'CC1=C(C=CC(=C1)F)NC(=O)...', qed: 0.812, sa: 2.41, dockScore: -9.4, logP: 2.8, mw: 372.4, pareto: true },
  { id: 'MOL-002', smiles: 'C1CN(CCN1)C2=NC(=NC...', qed: 0.741, sa: 2.89, dockScore: -8.9, logP: 1.9, mw: 341.2, pareto: true },
  { id: 'MOL-003', smiles: 'COC1=CC=C(C=C1)C2=NN...', qed: 0.698, sa: 3.12, dockScore: -8.4, logP: 2.2, mw: 324.3, pareto: false },
  { id: 'MOL-007', smiles: 'FC1=CC=C(C=C1)C2=NN...', qed: 0.881, sa: 1.98, dockScore: -7.2, logP: 1.5, mw: 298.3, pareto: true },
  { id: 'MOL-008', smiles: 'CC(=O)NC1=CC=C(C=C1)...', qed: 0.621, sa: 4.11, dockScore: -9.8, logP: 3.9, mw: 412.5, pareto: false },
  { id: 'MOL-009', smiles: 'N#CC1=CC=C(NC(=O)...', qed: 0.554, sa: 4.67, dockScore: -10.1, logP: 4.2, mw: 389.4, pareto: false },
  { id: 'MOL-010', smiles: 'OC1=CC=C(C=C1)CC2=CC...', qed: 0.772, sa: 2.22, dockScore: -8.7, logP: 2.1, mw: 311.3, pareto: true },
  { id: 'MOL-011', smiles: 'ClC1=CC=C(C=C1)C2=CN...', qed: 0.644, sa: 3.55, dockScore: -7.9, logP: 3.3, mw: 356.8, pareto: false },
];

export const MOCK_MD: MDTimepoint[] = Array.from({ length: 50 }, (_, i) => ({
  ns: i * 2,
  rmsd: 1.2 + Math.sin(i * 0.3) * 0.4 + Math.random() * 0.3,
  bindingEnergy: -42 - Math.cos(i * 0.25) * 8 + Math.random() * 3,
}));
