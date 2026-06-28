import os
import sys
import time
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

try:
    import oci
except ImportError as exc:
    raise SystemExit(f"Dependência 'oci' não instalada: {exc}") from exc

COMPARTMENT_ID = os.environ["OCI_COMPARTMENT_ID"]
SUBNET_ID = os.environ["OCI_SUBNET_ID"]
IMAGE_ID = os.environ["OCI_IMAGE_ID"]
SHAPE = os.environ.get("OCI_SHAPE", "VM.Standard.A1.Flex")
ADS = [ad.strip() for ad in os.environ.get("OCI_ADS", "qRwa:US-ASHBURN-AD-1,qRwa:US-ASHBURN-AD-2,qRwa:US-ASHBURN-AD-3").split(",") if ad.strip()]
SMTP_SENDER = os.environ["SMTP_SENDER"]
SMTP_RECIPIENT = os.environ["SMTP_RECIPIENT"]
SMTP_APP_PASSWORD = os.environ.get("SMTP_APP_PASSWORD", "")


def build_config():
    return {
        "user": os.environ["OCI_USER"],
        "fingerprint": os.environ["OCI_FINGERPRINT"],
        "key_content": os.environ["OCI_PRIVATE_KEY"].replace("\\n", "\n"),
        "tenancy": os.environ["OCI_TENANCY"],
        "region": os.environ["OCI_REGION"],
    }


def build_compute(config):
    return oci.core.ComputeClient(config)


def build_virtual_network(config):
    return oci.core.VirtualNetworkClient(config)


def parse_shape_config(ocpus, memory_gbs):
    return oci.core.models.LaunchInstanceShapeConfigDetails(
        ocpus=int(ocpus),
        memory_in_gbs=int(memory_gbs),
    )


def build_shape_config():
    primary_ocpus = os.environ.get("OCI_SHAPE_OCPUS", "4")
    primary_memory = os.environ.get("OCI_SHAPE_MEMORY_GBS", "24")
    fallback_ocpus = os.environ.get("OCI_SHAPE_FALLBACK_OCPUS", primary_ocpus)
    fallback_memory = os.environ.get("OCI_SHAPE_FALLBACK_MEMORY_GBS", primary_memory)
    return parse_shape_config(primary_ocpus, primary_memory), parse_shape_config(fallback_ocpus, fallback_memory)


def is_fallback_error(e):
    msg = str(e)
    return "Out of host capacity" in msg or "InternalError" in msg


def send_email(subject, body):
    if not SMTP_APP_PASSWORD:
        print("Senha do remetente ausente; não enviarei e-mail.")
        return
    try:
        msg = MIMEMultipart()
        msg["From"] = SMTP_SENDER
        msg["To"] = SMTP_RECIPIENT
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(SMTP_SENDER, SMTP_APP_PASSWORD)
            server.send_message(msg)
        print("Notificação enviada.")
    except Exception as e:
        print(f"Falha no e-mail: {e}")


def get_public_ip(compute_client, virtual_network_client, instance):
    try:
        attachments = compute_client.list_vnic_attachments(compartment_id=COMPARTMENT_ID, instance_id=instance.id).data
        for attachment in attachments:
            vnic = virtual_network_client.get_vnic(attachment.vnic_id).data
            if vnic.public_ip:
                return vnic.public_ip
    except Exception as e:
        print(f"Erro ao obter IP: {e}")
    return "Não disponível"


def build_body(compute_client, virtual_network_client, instance):
    return (
        f"Instância OCI: {instance.display_name}\n"
        f"OCID: {instance.id}\n"
        f"Estado: {instance.lifecycle_state}\n"
        f"IP público: {get_public_ip(compute_client, virtual_network_client, instance)}\n"
        f"Região: {instance.region}\n"
    )


def existing_instance(compute_client):
    try:
        instances = compute_client.list_instances(compartment_id=COMPARTMENT_ID, display_name="hermes-vm").data
        return instances[0] if instances else None
    except Exception as e:
        print(f"Falha ao listar instância: {e}")
        return None


def main():
    config = build_config()
    compute_client = build_compute(config)
    virtual_network_client = build_virtual_network(config)
    primary_shape, fallback_shape = build_shape_config()

    instance = existing_instance(compute_client)
    if instance:
        print("Instância já existe:")
        print(build_body(compute_client, virtual_network_client, instance))
        send_email("hermes-vm: instância existente", build_body(compute_client, virtual_network_client, instance))
        return 0

    def try_create(shape_config, label):
        for ad in ADS:
            print(f"Tentando criar VM no {ad} ({label}) ...")
            try:
                details = oci.core.models.LaunchInstanceDetails(
                    compartment_id=COMPARTMENT_ID,
                    availability_domain=ad,
                    shape=SHAPE,
                    shape_config=shape_config,
                    image_id=IMAGE_ID,
                    subnet_id=SUBNET_ID,
                    display_name="hermes-vm",
                    create_vnic_details=oci.core.models.CreateVnicDetails(assign_public_ip=True),
                )
                response = compute_client.launch_instance(launch_instance_details=details)
                instance = response.data
                print("Instância criada:")
                print(build_body(compute_client, virtual_network_client, instance))
                send_email(f"hermes-vm: instância criada ({label})", build_body(compute_client, virtual_network_client, instance))
                return True
            except Exception as e:
                msg = str(e)
                if "Out of host capacity" in msg or "InternalError" in msg:
                    print(f"Falhou no {ad} ({label}): sem capacidade.")
                else:
                    print(f"Falhou no {ad} ({label}): {e}")
        return False

    if try_create(primary_shape, "4 OCPUs / 24 GB"):
        return 0

    if (
        fallback_shape.ocpus != primary_shape.ocpus
        or fallback_shape.memory_in_gbs != primary_shape.memory_in_gbs
    ):
        if try_create(fallback_shape, "2 OCPUs / 12 GB"):
            return 0

    print("Nenhum AD disponível no momento.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
