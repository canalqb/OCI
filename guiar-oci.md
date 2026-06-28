# Guia Rápido: OCI no Windows + Terraform Tier (Free Tier)

Este guia é para quem está no Oracle Cloud **Free Tier / Always Free** e quer preparar a conta para usar o script `oci_vm.py` ou criar a instância manualmente.

---

## 1. Como instalar o OCI CLI no Windows

### Opção A (recomendada) — via MSI
1. Baixe o instalador MSI oficial:
   - https://github.com/oracle/oci-cli/releases/latest
   - Procure por `oci-cli-*-windows-x64-msi.pkg`
2. Execute o instalador.
3. Após instalar, abra um **novo** terminal (cmd, PowerShell ou Git Bash) e digite:
   ```bash
   oci --version
   ```
   Se mostrar um número de versão, está ok.

### Opção B — via Python e pip
Se você preferir usar a mesma Python já instalada:
```bash
pip install oci-cli --upgrade
oci --version
```
**Importante:** no Windows, use sempre um terminal com suporte a UTF-8 (Git Bash funciona bem).

---

## 2. Como configurar o OCI CLI

Rode:
```bash
oci setup config
```
Responda as perguntas:
- **Tenancy OCID:** copie do perfil do usuário no console OCI.
- **User OCID:** idem.
- **Fingerprint:** da chave pública que você vai gerar.
- **Path to private key:** caminho do arquivo `.pem`.
- **Region:** escolha `us-ashburn-1` ou outra que esteja disponível.

> **Nota:** no Free Tier / Always Free, **não é possível trocar a região** depois. A região fica fixa na sua conta. Se precisar mudar, terá que criar nova conta.
> Consulte sempre na internet e no console quais regiões estão com capacidade para Always Free. Em many cases, **Ashburn (iad)** tem sido a mais estável.

---

## 3. Pegando os OCIDs necessários

Você vai precisar desses valores para configurar os Secrets no GitHub Actions:

### 3.1 OCID do Tenancy
- No console OCI, clique no **ícone de perfil** no canto superior direito.
- **Tenancy**: `<seu-tenancy-name>`
- O nome completo com prefixo `ocid1.tenancy.oc1..` aparece na página **Tenancy Details**.

### 3.2 OCID do Usuário
- Menu: **Identity > Users**.
- Clique no usuário que você criou/usa.
- Copie o campo **OCID** (começa com `ocid1.user.oc1..`).

### 3.3 Fingerprint da chave API
- Você vai gerar um par de chaves RSA (abaixo).
- O fingerprint é exibido no console em **Identity > Users > <seu usuário> > API Keys** depois de adicionar a chave pública.

### 3.4 Criando API Key (chave pública/privada)
No Windows (Git Bash):
```bash
# Gera chave privada e pública
openssl genrsa -out ~/.oci/oci_api_key.pem 2048
openssl rsa -pubout -in ~/.oci/oci_api_key.pem -out ~/.oci/oci_api_key_public.pem

# Adiciona a chave pública no console:
# Identity > Users > <seu usuário> > Add Public Key
# Cole o conteúdo do arquivo oci_api_key_public.pem
```

### 3.5 OCID da Compartimento
- Menu: **Identity > Compartments**
- Clique no compartimento root (geralmente tem o mesmo nome do seu tenancy).
- Copie o **OCID** (começa com `ocid1.compartment.oc1..`).

### 3.6 OCID da Subnet
Depois de criar a VCN e subredes (veja item 4):
- Menu: **Networking > Virtual Cloud Networks**
- Clique na VCN > **Subnets**
- Copie o **OCID** da subnet pública que receberá a instância.

### 3.7 OCID da Imagem
- Menu: **Compute > Instances > Create Instance**
- Em **Image**, clique em **Change image** > **Oracle-provided images**
- Escolha a imagem desejada (recomendo **Oracle Linux**).
- Clique na imagem para ver detalhes ou use a CLI:
  ```bash
  oci compute image list --compartment-id ocid1.compartment.oc1..... --operating-system "Oracle Linux" --shape VM.Standard.A1.Flex --query "data[?contains(\"display-name\", \"Oracle Linux\")] | [0].id" --raw-output
  ```
- Copie o **OCID** da imagem.

---

## 4. Ordem correta para criar a VCN, Subredes e Gateway

**Importante:** não crie a instância primeiro sem o Internet Gateway configurado. Se você for obrigado a **deletar** a instância para corrigir a rede, perde a chance inicial de criar com a configuração desejada (4 OCPUs, 24 GB). Além disso, em Always Free, **a conta é apenas uma por CPF**.

### 4.1 VCN
1. Menu: **Networking > Virtual Cloud Networks > Create VCN**
2. Preencha:
   - **Name**: `vcn-hermes`
   - **IPv4 CIDR block**: `10.0.0.0/16`
   - **DNS label**: opcional
3. Clique em **Create VCN**.

### 4.2 Subrede Pública
- Dentro da VCN criada, vá em **Subnets > Create Subnet**
- Preencha:
  - **Name**: `subnet-public`
  - **CIDR block**: `10.0.0.0/24`
  - **Scope**: Public
- Crie.

### 4.3 Subrede Privada
- Mesma VCN, **Subnets > Create Subnet**
- Preencha:
  - **Name**: `subnet-private`
  - **CIDR block**: `10.0.1.0/24`
  - **Scope**: Private
- Crie.

### 4.4 Internet Gateway
- Na VCN, vá em **Internet Gateways > Create Internet Gateway**
- **Name**: `igw-hermes`
- Crie.

### 4.5 Route Table (para trafego público)
- Na VCN, vá em **Route Tables > Default Route Table for VCN**
- Edite a regra padrão:
  - **Destination CIDR**: `0.0.0.0/0`
  - **Target**: selecione o `igw-hermes`
- Salve.

### 4.6 Security List (liberar porta 22 para SSH)
- Na VCN, vá em **Security Lists > Default Security List for VCN** (ou crie um novo)
- Edite as **Ingress Rules**:
  - **Source CIDR**: `0.0.0.0/0`
  - **Destination Port Range**: `22`
  - **Protocol**: `TCP`
- Salve.

Agora sim, com VCN, subredes, Internet Gateway e tabela de rotas prontas, crie a instância na subnet pública.

---

## 5. Dificuldade para criar instâncias no Free Tier

No Always Free, a oferta padrão é limitada. O shape `VM.Standard.A1.Flex` (baseado em ARM Ampere) com **4 OCPUs e 24 GB** costuma ter capacidade variável por região e por domínio de disponibilidade (AD). É comum receber erro:
```
Out of host capacity
```
Justamente por isso estamos desenvolvendo este script automático: ele fica tentando a cada 10 minutos nos ADs 1, 2 e 3 de `US-ASHBURN-1` até que haja recurso disponível.

### Pontos importantes:
- Não crie a instância manualmente antes de preparar a VCN, subnet pública, Internet Gateway e tabelas de rota.
- Se a capacidade faltar, **não force a criação com shape/quantidade diferente**; espere a liberação para manter a configuração ideal.
- No script, usamos retry automático e notificação por e-mail assim que a VM for criada ou se já existir.
- Cada conta Free Tier é **uma por CPF**.

---

## 6. Resumo dos dados necessários para o GitHub Actions

Preencha os Secrets em `https://github.com/canalqb/OCI/settings/secrets/actions`:

| Secret | Onde pegar |
|---|---|
| `SMTP_SENDER` | a conta Gmail que envia (use senha de app) |
| `SMTP_RECIPIENT` | para quem receber a notificação |
| `SMTP_APP_PASSWORD` | senha de app do Gmail |
| `OCI_USER` | OCID do usuário em **Identity > Users** |
| `OCI_FINGERPRINT` | fingerprint da API key |
| `OCI_PRIVATE_KEY` | conteúdo do arquivo `~/.oci/oci_api_key.pem` |
| `OCI_TENANCY` | OCID do tenancy |
| `OCI_REGION` | ex: `us-ashburn-1` |
| `OCI_COMPARTMENT_ID` | OCID do compartimento |
| `OCI_SUBNET_ID` | OCID da subnet pública |
| `OCI_IMAGE_ID` | OCID da imagem Oracle Linux (compatible with A1) |
| `OCI_SHAPE` | `VM.Standard.A1.Flex` |
| `OCI_SHAPE_OCPUS` | `4` |
| `OCI_SHAPE_MEMORY_GBS` | `24` |
| `OCI_ADS` | `qRwa:US-ASHBURN-AD-1,qRwa:US-ASHBURN-AD-2,qRwa:US-ASHBURN-AD-3` |

---

## 7. Próximos passos

1. Instal o OCI CLI no Windows (seção 1).
2. Rode `oci setup config` e gere as API Keys (seção 2 e 3.4).
3. Crie VCN, subredes, Internet Gateway e regras (seção 4).
4. Pegue todos os OCIDs necessários (seção 3).
5. Preencha os Secrets no GitHub (seção 6).
6. O GitHub Actions vai rodar sozinho a cada 10 minutos; quando houver espaço, a instância será criada e você receberá e-mail.

---

Dúvidas comuns:
- **Posso mudar de região depois?** Não, no tier não. Planeje antes.
- **Posso expandir sem pagar?** Mantenha-se nos limites Always Free.
- **E se eu deletar a instância?** O script recria, mas se ela foi criada e depois deletada só por falta de rede configurada, o slot pode demorar mais para liberar.
