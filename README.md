# OCI VM Automator

Executa o provisionamento da instância OCI `hermes-vm` em `qRwa:US-ASHBURN-AD-1/2/3` a cada 10 minutos.

Se a instância já existir, apenas notifica por e-mail com o IP público e estado.

Fluxo:
- Checa existência da instância `hermes-vm`
- Tenta criação nos 3 ADs
- Notifica `qrodrigob@gmail.com` a partir de `airdropqb@gmail.com`

Segredos sensíveis ficam em GitHub Secrets. Nada de segredo no repositório.
