#!/usr/bin/env bash
# Verify native NetworkPolicy enforcement with short-lived authorized Pods.
# This script never turns a missing prerequisite into a pass.
set -Eeuo pipefail

: "${CNI_IDENTITY:?Set CNI_IDENTITY to the verified native CNI/controller identity.}"
: "${DIAGNOSTIC_IMAGE:?Set DIAGNOSTIC_IMAGE to an approved image pinned by digest.}"
CONTEXT="${KUBE_CONTEXT:-belacca-native}"
DIAG_NS="${DIAG_NS:-network-policy-diagnostics}"
ROOM_SERVICE="${ROOM_SERVICE:-}"
EVIDENCE_FILE="${EVIDENCE_FILE:-/tmp/native-network-policy-evidence.txt}"

fail() { echo "FAIL: $*" >&2; exit 1; }
service_ip() { kubectl -n "$1" get svc "$2" -o jsonpath='{.spec.clusterIP}'; }

[[ "$(kubectl config current-context)" == "$CONTEXT" ]] || fail "kubectl context is not $CONTEXT"
kubectl version >/dev/null 2>&1 || fail "kubectl cannot reach the selected cluster"
[[ -n "$ROOM_SERVICE" ]] || fail "ROOM_SERVICE must name a live pong-room-<id> Service created by the normal room lifecycle"

api_ip="$(service_ip default kubernetes)"
[[ "$api_ip" == "10.43.0.1" ]] || fail "Kubernetes Service IP is $api_ip, expected 10.43.0.1; review policy CIDR before continuing"
room_ip="$(service_ip pong "$ROOM_SERVICE")"
[[ -n "$room_ip" && "$room_ip" != "None" ]] || fail "room Service has no ClusterIP: $ROOM_SERVICE"
api_pod_ip="$(kubectl -n pong get pod -l app=cloudnativepong,component=api -o jsonpath='{.items[0].status.podIP}')"
[[ -n "$api_pod_ip" ]] || fail "Pong API Pod IP unavailable"
dex_ip="$(service_ip dex dex)"
flux_ip="$(service_ip flux-system kustomize-controller)"
longhorn_manager_ip="$(kubectl -n longhorn-system get pod -l app=longhorn-manager -o jsonpath='{.items[0].status.podIP}')"
[[ -n "$longhorn_manager_ip" ]] || fail "Longhorn manager Pod IP unavailable"
kubectl -n longhorn-system get networkpolicy longhorn-manager >/dev/null || fail "Longhorn chart-owned manager NetworkPolicy is not present"

mkdir -p "$(dirname "$EVIDENCE_FILE")"
: >"$EVIDENCE_FILE"
{
  echo "contract=belacca.native-network-policy.v1"
  echo "context=$CONTEXT"
  echo "cni_identity=$CNI_IDENTITY"
  echo "diagnostic_image=$DIAGNOSTIC_IMAGE"
  echo "service_cidr_check=kubernetes.default=$api_ip expected=10.43.0.1"
  echo "room_service=$ROOM_SERVICE"
  echo "room_service_ip=$room_ip"
  echo "started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
} >>"$EVIDENCE_FILE"

cleanup() {
  kubectl -n pong delete pod np-gateway-source np-api-source np-room-source --ignore-not-found --wait=false >/dev/null 2>&1 || true
  kubectl -n observability delete pod np-prometheus-source --ignore-not-found --wait=false >/dev/null 2>&1 || true
  kubectl -n analytics delete pod np-analytics-auth-source --ignore-not-found --wait=false >/dev/null 2>&1 || true
  kubectl -n headlamp delete pod np-headlamp-auth-source --ignore-not-found --wait=false >/dev/null 2>&1 || true
  kubectl -n longhorn-system delete pod np-longhorn-source --ignore-not-found --wait=false >/dev/null 2>&1 || true
  kubectl delete namespace "$DIAG_NS" --ignore-not-found --wait=false >/dev/null 2>&1 || true
}
trap cleanup EXIT
cleanup
kubectl create namespace "$DIAG_NS" --dry-run=client -o yaml | kubectl apply -f - >/dev/null

apply_probe() {
  local namespace="$1" name="$2" labels="$3" label_block=""
  if [[ -n "$labels" ]]; then
    label_block=$'  labels:\n'"$labels"
  fi
  kubectl -n "$namespace" apply -f - >/dev/null <<EOF
apiVersion: v1
kind: Pod
metadata:
  name: $name
$label_block
spec:
  automountServiceAccountToken: false
  activeDeadlineSeconds: 300
  restartPolicy: Never
  containers:
    - name: probe
      image: $DIAGNOSTIC_IMAGE
      command: ["sh", "-c", "sleep 300"]
EOF
}
apply_probe pong np-gateway-source '    app: cloudnativepong
    component: gateway'
apply_probe pong np-api-source '    app: cloudnativepong
    component: api'
apply_probe pong np-room-source '    app: cloudnativepong
    role: room'
apply_probe observability np-prometheus-source '    app.kubernetes.io/name: prometheus
    belacca.com/stage: native-production'
apply_probe analytics np-analytics-auth-source '    app: oauth2-proxy'
apply_probe headlamp np-headlamp-auth-source '    app: oauth2-proxy'
apply_probe longhorn-system np-longhorn-source '    app: longhorn-manager'
apply_probe "$DIAG_NS" np-forbidden-source ''

for item in \
  pong/np-gateway-source pong/np-api-source pong/np-room-source \
  observability/np-prometheus-source analytics/np-analytics-auth-source \
  headlamp/np-headlamp-auth-source longhorn-system/np-longhorn-source \
  "$DIAG_NS"/np-forbidden-source; do
  namespace="${item%/*}"; pod="${item#*/}"
  kubectl -n "$namespace" wait --for=condition=Ready "pod/$pod" --timeout=90s >/dev/null
 done

exec_probe() {
  local id="$1" namespace="$2" pod="$3" command="$4"
  if kubectl -n "$namespace" exec "$pod" -- sh -c "$command" >/dev/null 2>&1; then
    echo "required,$id,pass" | tee -a "$EVIDENCE_FILE"
  else
    echo "required,$id,fail" | tee -a "$EVIDENCE_FILE"
    fail "required edge failed: $id"
  fi
}
forbidden_probe() {
  local id="$1" command="$2"
  if kubectl -n "$DIAG_NS" exec np-forbidden-source -- sh -c "$command" >/dev/null 2>&1; then
    echo "forbidden,$id,fail" | tee -a "$EVIDENCE_FILE"
    fail "forbidden edge was reachable: $id"
  else
    echo "forbidden,$id,pass" | tee -a "$EVIDENCE_FILE"
  fi
}

# Pong graph: gateway -> static/API, API -> dynamic room, room -> callback.
exec_probe gateway-static pong np-gateway-source "wget -q -T 5 -O - http://pong-static.pong.svc.cluster.local/health"
exec_probe gateway-api pong np-gateway-source "wget -q -T 5 -O - http://pong-api.pong.svc.cluster.local/health"
exec_probe api-room pong np-api-source "wget -q -T 5 -O - http://$room_ip:8080/health"
exec_probe room-callback pong np-room-source "wget -q -T 5 -O - http://$api_pod_ip:8080/health"
exec_probe api-kubernetes-api pong np-api-source "wget -q -T 5 --no-check-certificate -O - https://$api_ip:443/version"
exec_probe pong-dns pong np-api-source "nslookup pong-api.pong.svc.cluster.local"

# Observability -> Pong and Flux, and chart-owned Longhorn manager peer path.
exec_probe prometheus-pong observability np-prometheus-source "wget -q -T 5 -O - http://pong-api.pong.svc.cluster.local:8080/metrics"
exec_probe prometheus-flux observability np-prometheus-source "wget -q -T 5 -O - http://$flux_ip:8080/metrics"
exec_probe longhorn-storage longhorn-system np-longhorn-source "wget -q -T 5 -O - http://$longhorn_manager_ip:9500/v1"

# Identity/analytics callbacks: auth proxies reach the public Dex issuer via
# declared native node addresses and their in-namespace upstreams.
exec_probe analytics-dex analytics np-analytics-auth-source "wget -q -T 8 --no-check-certificate -O - https://dashboard.belacca.com/oauth2/.well-known/openid-configuration"
exec_probe analytics-upstream analytics np-analytics-auth-source "wget -q -T 5 -O - http://goatcounter.analytics.svc.cluster.local:80/status"
exec_probe headlamp-dex headlamp np-headlamp-auth-source "wget -q -T 8 --no-check-certificate -O - https://dashboard.belacca.com/oauth2/.well-known/openid-configuration"
exec_probe headlamp-upstream headlamp np-headlamp-auth-source "wget -q -T 5 -O - http://headlamp.headlamp.svc.cluster.local:80/"

# Actual host-network Traefik edge; this is not replaced by a same-label Pod.
if curl --fail --silent --show-error --max-time 10 --resolve pong.belacca.com:443:169.58.97.73 https://pong.belacca.com/health >/dev/null; then
  echo "required,traefik-gateway,pass" | tee -a "$EVIDENCE_FILE"
else
  echo "required,traefik-gateway,fail" | tee -a "$EVIDENCE_FILE"
  fail "required edge failed: traefik-gateway"
fi

# A clean namespace with no allow labels must not reach isolated targets.
forbidden_probe diagnostic-to-pong-api "wget -q -T 3 -O - http://$api_pod_ip:8080/health"
forbidden_probe diagnostic-to-room "wget -q -T 3 -O - http://$room_ip:8080/health"
forbidden_probe diagnostic-to-dex "nc -z -w 3 $dex_ip 5556"
forbidden_probe diagnostic-to-flux "nc -z -w 3 $flux_ip 8080"
forbidden_probe diagnostic-to-longhorn "nc -z -w 3 $longhorn_manager_ip 9500"

kubectl -n pong delete pod np-gateway-source np-api-source np-room-source --wait=true --timeout=60s >/dev/null
kubectl -n observability delete pod np-prometheus-source --wait=true --timeout=60s >/dev/null
kubectl -n analytics delete pod np-analytics-auth-source --wait=true --timeout=60s >/dev/null
kubectl -n headlamp delete pod np-headlamp-auth-source --wait=true --timeout=60s >/dev/null
kubectl -n longhorn-system delete pod np-longhorn-source --wait=true --timeout=60s >/dev/null
kubectl -n "$DIAG_NS" delete pod np-forbidden-source --wait=true --timeout=60s >/dev/null
echo "cleanup,diagnostic-workloads,pass" | tee -a "$EVIDENCE_FILE"
echo "CNI enforcement demonstrated: required and forbidden edge probes passed"
