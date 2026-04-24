// ═══════════════════════════════════════════════════════════════
// NEXUS CLOSER — Client Identity Config
// Fonte única de identidade do cliente (White-Label).
// NUNCA hardcodar nome de empresa em outros arquivos.
// ═══════════════════════════════════════════════════════════════
window.NEXUS_CLIENT = {
  name: "[EMPRESA]",
  logo: "web/assets/client_logo.svg",
  color_accent: "#00FF41",

  // Identidade do Vendedor — usada nos relatórios PULSE (PDF)
  // NÃO incluir CPF, RG, CNPJ, valores de comissão ou salário
  vendor: {
    nome:    "[NOME DO CLOSER]",
    cargo:   "[CARGO]",
    empresa: "[EMPRESA]",
    email:   "[EMAIL]",
    cidade:  "[CIDADE — UF]",
  },
};
