resource "helm_release" "nginx_gateway" {
  name             = "ngf"
  repository       = "oci://ghcr.io/nginx/charts"
  chart            = "nginx-gateway-fabric"
  namespace        = "nginx-gateway"
  create_namespace = true

  depends_on = [module.eks]
}