resource "null_resource" "gateway_api_crds" {
  provisioner "local-exec" {
    command = "aws eks update-kubeconfig --region ap-south-1 --name todo-eks && kubectl apply -f https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.3.0/standard-install.yaml"
  }

  depends_on = [module.eks]
}

resource "helm_release" "nginx_gateway" {
  name             = "ngf"
  repository       = "oci://ghcr.io/nginx/charts"
  chart            = "nginx-gateway-fabric"
  namespace        = "nginx-gateway"
  create_namespace = true
  depends_on = [null_resource.gateway_api_crds]
}