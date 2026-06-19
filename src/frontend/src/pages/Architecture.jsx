export default function Architecture() {
  return (
    <div>
      <h2 className="text-2xl font-bold text-purple-400 mb-2">System Architecture</h2>
      <p className="text-gray-400 mb-6">
        VidCast infrastructure running on AWS EKS (eu-west-2). Traffic enters via an
        Application Load Balancer, passes through nginx Ingress, and fans out to the
        microservices. Platform tooling (Argo CD, Prometheus, Grafana, Kyverno) runs
        alongside the app workloads in-cluster.
      </p>

      <div className="bg-indigo-950 border border-indigo-800 rounded-xl p-4 flex justify-center">
        <img
          src="/vidcast_infrastructure_architecture.png"
          alt="VidCast infrastructure architecture diagram — AWS EKS cluster in eu-west-2 showing ALB, nginx Ingress, Gateway, Auth, Converter, Notification services, RabbitMQ, MongoDB GridFS, PostgreSQL, Redis, and platform tooling (Argo CD, Prometheus, Grafana, Kyverno, External Secrets)"
          className="max-w-full rounded-lg"
        />
      </div>
    </div>
  )
}
