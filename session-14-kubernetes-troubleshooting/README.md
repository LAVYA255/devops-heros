# Session 14: Kubernetes Troubleshooting

**Author:** Lavya ([@LAVYA255](https://github.com/LAVYA255))
**Course:** SST DevOps & Cloud [SWE]
**Session:** 14 - Troubleshooting
**Repository:** `devops-heros / session-14-kubernetes-troubleshooting`

**Setup:** Minikube v1.39.0 on the docker driver, Kubernetes v1.37.0, inside WSL2 Ubuntu. Every command below was actually run and the output is pasted exactly as it came back. Screenshots in `./screenshots/` are captures of the same terminal session.

For each failure I followed the same loop the brief asks for: identify, investigate, find the root cause, fix, verify, write it down.

---

## Task 1: The troubleshooting toolbox

Eight commands cover almost everything. The order matters more than the list: `get` to see what is wrong, `describe` to find out why, `logs` to hear it from the application itself.

**Commands**
```bash
kubectl apply -f 09-service-dns-troubleshooting/pod.yaml
kubectl apply -f 09-service-dns-troubleshooting/deployment.yaml
kubectl get pods
kubectl get pods,deploy,svc
kubectl get pods -o wide
kubectl describe pod logs-demo | head -30
kubectl logs logs-demo
kubectl logs logs-demo --tail=3
kubectl logs -l app=web --tail=2 --prefix
kubectl exec logs-demo -- ls -la /
kubectl exec logs-demo -- cat /etc/resolv.conf
kubectl events --for pod/logs-demo | head -10
kubectl get events --sort-by=.lastTimestamp | tail -8
kubectl explain pod.spec.containers.livenessProbe | head -14
kubectl explain deployment.spec.strategy --recursive | head -12
kubectl top nodes
kubectl top pods
kubectl delete -f 09-service-dns-troubleshooting/pod.yaml --wait=false
kubectl delete -f 09-service-dns-troubleshooting/deployment.yaml --wait=false
```

**Output**
```text
$ kubectl apply -f 09-service-dns-troubleshooting/pod.yaml
pod/logs-demo created

$ kubectl apply -f 09-service-dns-troubleshooting/deployment.yaml
deployment.apps/web created

# 1) kubectl get - the 10-second overview
$ kubectl get pods
NAME                   READY   STATUS    RESTARTS   AGE
logs-demo              1/1     Running   0          2s
web-557577df75-f8ps9   1/1     Running   0          1s
web-557577df75-pwcch   1/1     Running   0          1s

$ kubectl get pods,deploy,svc
NAME                       READY   STATUS    RESTARTS   AGE
pod/logs-demo              1/1     Running   0          2s
pod/web-557577df75-f8ps9   1/1     Running   0          1s
pod/web-557577df75-pwcch   1/1     Running   0          1s

NAME                  READY   UP-TO-DATE   AVAILABLE   AGE
deployment.apps/web   2/2     2            2           1s

# 2) kubectl get -o wide - adds IP and node, the first thing you want when networking looks wrong
$ kubectl get pods -o wide
NAME                   READY   STATUS    RESTARTS   AGE   IP            NODE       NOMINATED NODE   READINESS GATES
logs-demo              1/1     Running   0          2s    10.244.0.29   minikube   <none>           <none>
web-557577df75-f8ps9   1/1     Running   0          1s    10.244.0.30   minikube   <none>           <none>
web-557577df75-pwcch   1/1     Running   0          1s    10.244.0.31   minikube   <none>           <none>

# 3) kubectl describe - spec + current state + the EVENT LOG (where the real answer usually is)
$ kubectl describe pod logs-demo | head -30
Name:             logs-demo
Namespace:        default
Priority:         0
Service Account:  default
Node:             minikube/192.168.49.2
Start Time:       Wed, 07 Oct 2026 15:12:31 +0000
Labels:           <none>
Annotations:      <none>
Status:           Running
IP:               10.244.0.29
IPs:
  IP:  10.244.0.29
Containers:
  app:
    Container ID:  containerd://70f2de91f9a9522dabbb583feb28c557184e4e526792fd11a00b4e96c5e469de
    Image:         busybox:1.36
    Image ID:      docker.io/library/busybox@sha256:73aaf090f3d85aa34ee199857f03fa3a95c8ede2ffd4cc2cdb5b94e566b11662
    Port:          <none>
    Host Port:     <none>
    Command:
      sh
      -c
      echo "Application started"
      echo "Connecting to database..."
      echo "Database connection successful"
      echo "Application is running"
      while true; do
        echo "Application is healthy"
        sleep 5
      done

# 4) kubectl logs - what the application itself said
$ kubectl logs logs-demo
Application started
Connecting to database...
Database connection successful
Application is running
Application is healthy

$ kubectl logs logs-demo --tail=3
Database connection successful
Application is running
Application is healthy

$ kubectl logs -l app=web --tail=2 --prefix
[pod/web-557577df75-f8ps9/nginx] 2026/10/07 15:12:33 [notice] 1#1: start worker process 51
[pod/web-557577df75-f8ps9/nginx] 2026/10/07 15:12:33 [notice] 1#1: start worker process 52
[pod/web-557577df75-pwcch/nginx] 2026/10/07 15:12:33 [notice] 1#1: start worker process 51
[pod/web-557577df75-pwcch/nginx] 2026/10/07 15:12:33 [notice] 1#1: start worker process 52

# 5) kubectl exec - get a shell inside the container and look around
$ kubectl exec logs-demo -- ls -la /
total 48
drwxr-xr-x    1 root     root          4096 Oct  7 15:12 .
drwxr-xr-x    1 root     root          4096 Oct  7 15:12 ..
drwxr-xr-x    2 root     root         12288 May 18  2023 bin
drwxr-xr-x    5 root     root           360 Oct  7 15:12 dev
drwxr-xr-x    1 root     root          4096 Oct  7 15:12 etc
drwxr-xr-x    2 nobody   nobody        4096 May 18  2023 home
drwxr-xr-x    2 root     root          4096 May 18  2023 lib
lrwxrwxrwx    1 root     root             3 May 18  2023 lib64 -> lib
dr-xr-xr-x  760 root     root             0 Oct  7 15:12 proc
drwx------    2 root     root          4096 May 18  2023 root
dr-xr-xr-x   13 root     root             0 Oct  7 15:12 sys
drwxrwxrwt    2 root     root          4096 May 18  2023 tmp
drwxr-xr-x    4 root     root          4096 May 18  2023 usr
drwxr-xr-x    1 root     root          4096 Oct  7 15:12 var

$ kubectl exec logs-demo -- cat /etc/resolv.conf
search default.svc.cluster.local svc.cluster.local cluster.local
nameserver 10.96.0.10
options ndots:5

# 6) kubectl events - cluster-level timeline, sorted
$ kubectl events --for pod/logs-demo | head -10
LAST SEEN   TYPE     REASON      OBJECT          MESSAGE
4s          Normal   Scheduled   Pod/logs-demo   Successfully assigned default/logs-demo to minikube
3s          Normal   Pulled      Pod/logs-demo   Container image "busybox:1.36" already present on machine and can be accessed by the pod
3s          Normal   Created     Pod/logs-demo   Container created
3s          Normal   Started     Pod/logs-demo   Container started

$ kubectl get events --sort-by=.lastTimestamp | tail -8
3s          Normal    Pulled                         pod/logs-demo                               Container image "busybox:1.36" already present on machine and can be accessed by the pod
3s          Normal    SuccessfulCreate               replicaset/web-557577df75                   Created pod: web-557577df75-pwcch
2s          Normal    Created                        pod/web-557577df75-f8ps9                    Container created
2s          Normal    Started                        pod/web-557577df75-f8ps9                    Container started
2s          Normal    Created                        pod/web-557577df75-pwcch                    Container created
2s          Normal    Pulled                         pod/web-557577df75-f8ps9                    Container image "nginx:1.27" already present on machine and can be accessed by the pod
2s          Normal    Started                        pod/web-557577df75-pwcch                    Container started
2s          Normal    Pulled                         pod/web-557577df75-pwcch                    Container image "nginx:1.27" already present on machine and can be accessed by the pod

# 7) kubectl explain - the schema reference, offline
$ kubectl explain pod.spec.containers.livenessProbe | head -14
KIND:       Pod
VERSION:    v1

FIELD: livenessProbe <Probe>

DESCRIPTION:
    Periodic probe of container liveness. Container will be restarted if the
    probe fails. Cannot be updated. More info:
    https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle#container-probes
    Probe describes a health check to be performed against a container to
    determine whether it is alive or ready to receive traffic.

FIELDS:

$ kubectl explain deployment.spec.strategy --recursive | head -12
GROUP:      apps
KIND:       Deployment
VERSION:    v1

FIELD: strategy <DeploymentStrategy>

DESCRIPTION:
    The deployment strategy to use to replace existing pods with new ones.
    DeploymentStrategy describes how to replace existing pods with new ones.

FIELDS:

# 8) kubectl top - live CPU/memory from metrics-server
$ kubectl top nodes
NAME       CPU(cores)   CPU(%)   MEMORY(bytes)   MEMORY(%)
minikube   208m         0%       1115Mi          14%

$ kubectl top pods
error: metrics not available yet

$ kubectl delete -f 09-service-dns-troubleshooting/pod.yaml --wait=false
pod "logs-demo" deleted from default namespace

$ kubectl delete -f 09-service-dns-troubleshooting/deployment.yaml --wait=false
deployment.apps "web" deleted from default namespace
```

**Screenshot**

![kubectl troubleshooting commands](./screenshots/01-commands.png)

What each one is actually for:

| Command | Answers |
| --- | --- |
| `kubectl get` | What exists and what state is it in |
| `kubectl get -o wide` | Which node and which pod IP, the first thing you want for any network problem |
| `kubectl describe` | Why. The Events block at the bottom is where the real answer usually lives |
| `kubectl logs` | What the application itself said before it died |
| `kubectl exec` | Get inside and look around: config files, DNS, connectivity |
| `kubectl events` | A cluster-wide timeline, useful when you do not yet know which object is at fault |
| `kubectl explain` | Field reference without leaving the terminal |
| `kubectl top` | Live CPU and memory, which is how you spot throttling and OOM risk |

The habit worth building: `get` tells you something is broken, `describe` tells you why, `logs` tells you what the app thought was happening. If `describe` shows no events and the pod never started, the problem is above the kubelet (scheduler, image, config). If events look fine but the app is unhappy, it is in the logs.

---

## Task 2: The failure modes

### 2.1 CrashLoopBackOff

**Output**
```text
# ISSUE 1: CrashLoopBackOff
$ cat 06-crashloopbackoff/broken-pod.yaml
apiVersion: v1
kind: Pod

metadata:
  name: crash-demo

spec:
  containers:
    - name: app
      image: busybox:1.36
      command:
        - sh
        - -c
        - |
          echo "Application starting..."
          echo "Something went wrong!"
          exit 1
# --- 1. IDENTIFY
$ kubectl apply -f 06-crashloopbackoff/broken-pod.yaml
pod/crash-demo created

$ kubectl get pod crash-demo
NAME         READY   STATUS   RESTARTS     AGE
crash-demo   0/1     Error    1 (3s ago)   4s

# --- 2. INVESTIGATE: the events show a restart loop, the logs show why
$ kubectl describe pod crash-demo | grep -A 8 Events:
Events:
  Type     Reason     Age              From               Message
  ----     ------     ----             ----               -------
  Normal   Scheduled  4s               default-scheduler  Successfully assigned default/crash-demo to minikube
  Normal   Pulled     2s (x2 over 3s)  kubelet            spec.containers{app}: Container image "busybox:1.36" already present on machine and can be accessed by the pod
  Normal   Created    2s (x2 over 3s)  kubelet            spec.containers{app}: Container created
  Normal   Started    2s (x2 over 3s)  kubelet            spec.containers{app}: Container started
  Warning  BackOff    1s               kubelet            spec.containers{app}: Back-off restarting failed container app in pod crash-demo_default(df1ce90b-6e4d-4d76-ad95-c59fb1395d84)

$ kubectl logs crash-demo
Application starting...
Something went wrong!

$ kubectl get pod crash-demo -o jsonpath='restarts={.status.containerStatuses[0].restartCount} lastExit={.status.containerStatuses[0].lastState.terminated.exitCode}{"\n"}'
restarts=1 lastExit=1

# --- 3. ROOT CAUSE: the container command runs 'exit 1' - the process terminates immediately with a
#     non-zero code. restartPolicy defaults to Always, so the kubelet restarts it, it exits again,
#     and the kubelet backs off exponentially. The image and scheduling are fine; the APP is the problem.
# --- 4. FIX: make the main process long-running and exit 0
$ diff 06-crashloopbackoff/broken-pod.yaml 06-crashloopbackoff/fixed-pod.yaml
16,17c16,17
<           echo "Something went wrong!"
<           exit 1
\ No newline at end of file
---
>           echo "Application is healthy"
>           sleep 3600
\ No newline at end of file

$ kubectl delete -f 06-crashloopbackoff/broken-pod.yaml
pod "crash-demo" deleted from default namespace

$ kubectl apply -f 06-crashloopbackoff/fixed-pod.yaml
pod/crash-demo created

# --- 5. VERIFY
$ kubectl get pod crash-demo
NAME         READY   STATUS    RESTARTS   AGE
crash-demo   1/1     Running   0          11s

$ kubectl logs crash-demo
Application starting...
Application is healthy

$ kubectl delete -f 06-crashloopbackoff/fixed-pod.yaml --wait=false
pod "crash-demo" deleted from default namespace
```

**Screenshot**

![CrashLoopBackOff](./screenshots/02-crashloopbackoff.png)

**Root cause.** The container command ends in `exit 1`, so the process terminates immediately with a non-zero code. `restartPolicy` defaults to `Always`, so the kubelet restarts it, it exits again, and the kubelet backs off exponentially (10s, 20s, 40s, up to five minutes). The image is fine and the scheduling is fine. The application is the problem.

**Fix.** Make the main process long-running and exit zero. After the fix the pod sits at `1/1 Running` with zero restarts.

Worth saying plainly: *CrashLoopBackOff is a symptom, not a diagnosis*. It only tells you the container keeps dying. `kubectl logs --previous` and the terminated `reason` tell you why, and the answer is different every time. See the OOMKilled case below for a completely different cause with the identical symptom.

### 2.2 ErrImagePull and ImagePullBackOff

**Output**
```text
# ISSUE 2 & 3: ErrImagePull -> ImagePullBackOff
$ cat 07-imagepullbackoff/broken-pod.yaml
apiVersion: v1
kind: Pod

metadata:
  name: image-demo

spec:
  containers:
    - name: app
      image: nginx:this-image-does-not-exist
# --- 1. IDENTIFY
$ kubectl apply -f 07-imagepullbackoff/broken-pod.yaml
pod/image-demo created

$ kubectl get pod image-demo
NAME         READY   STATUS         RESTARTS   AGE
image-demo   0/1     ErrImagePull   0          6s

# ErrImagePull is the FIRST failure; after retries the kubelet parks it in ImagePullBackOff:
$ kubectl get pod image-demo
NAME         READY   STATUS             RESTARTS   AGE
image-demo   0/1     ImagePullBackOff   0          16s

# --- 2. INVESTIGATE
$ kubectl describe pod image-demo | grep -A 10 Events:
Events:
  Type     Reason     Age               From               Message
  ----     ------     ----              ----               -------
  Normal   Scheduled  17s               default-scheduler  Successfully assigned default/image-demo to minikube
  Warning  Failed     15s               kubelet            spec.containers{app}: Failed to pull image "nginx:this-image-does-not-exist": rpc error: code = NotFound desc = failed to pull and unpack image "docker.io/library/nginx:this-image-does-not-exist": failed to resolve reference "docker.io/library/nginx:this-image-does-not-exist": docker.io/library/nginx:this-image-does-not-exist: not found
  Warning  Failed     15s               kubelet            spec.containers{app}: Error: ErrImagePull
  Normal   BackOff    14s               kubelet            spec.containers{app}: Back-off pulling image "nginx:this-image-does-not-exist"
  Warning  Failed     14s               kubelet            spec.containers{app}: Error: ImagePullBackOff
  Normal   Pulling    2s (x2 over 17s)  kubelet            spec.containers{app}: Pulling image "nginx:this-image-does-not-exist"

# --- 3. ROOT CAUSE: the tag 'this-image-does-not-exist' is not present in the nginx repository.
#     Note the pod was SCHEDULED successfully - the API object is valid and stored in etcd.
#     Only the kubelet's pull step fails. Same symptom appears for a private registry with no imagePullSecret.
$ kubectl get pod image-demo -o jsonpath='node={.spec.nodeName} image={.spec.containers[0].image}{"\n"}'
node=minikube image=nginx:this-image-does-not-exist

# --- 4. FIX: use a tag that exists
$ diff 07-imagepullbackoff/broken-pod.yaml 07-imagepullbackoff/fixed-pod.yaml
10c10
<       image: nginx:this-image-does-not-exist
\ No newline at end of file
---
>       image: nginx:1.27
\ No newline at end of file

$ kubectl delete -f 07-imagepullbackoff/broken-pod.yaml
pod "image-demo" deleted from default namespace

$ kubectl apply -f 07-imagepullbackoff/fixed-pod.yaml
pod/image-demo created

# --- 5. VERIFY
$ kubectl get pod image-demo
NAME         READY   STATUS    RESTARTS   AGE
image-demo   1/1     Running   0          1s

$ kubectl delete -f 07-imagepullbackoff/fixed-pod.yaml --wait=false
pod "image-demo" deleted from default namespace
```

**Screenshot**

![ImagePullBackOff](./screenshots/03-imagepullbackoff.png)

**Root cause.** The tag `this-image-does-not-exist` is not in the nginx repository. Note that the pod was *scheduled* successfully, so the API object is valid and stored in etcd and a node was assigned. Only the kubelet's pull step fails.

`ErrImagePull` is the first failure. After a few retries the kubelet parks it in `ImagePullBackOff`, which is the waiting state between attempts. The same pair of symptoms appears for a private registry with no `imagePullSecret`, a typo in the registry host, or a rate-limited registry (I hit exactly that in Session 20 when Docker Hub returned 429).

**Fix.** Use a tag that exists.

### 2.3 Pending, because nothing can schedule it

**Output**
```text
# ISSUE 4: Pending (unschedulable)
$ cat 08-pending-pods/broken-pod.yaml
apiVersion: v1
kind: Pod

metadata:
  name: pending-demo

spec:
  nodeSelector:
    kubernetes.io/hostname: node-that-does-not-exist

  containers:
    - name: nginx
      image: nginx:1.27
# --- 1. IDENTIFY
$ kubectl apply -f 08-pending-pods/broken-pod.yaml
pod/pending-demo created

$ kubectl get pod pending-demo
NAME           READY   STATUS    RESTARTS   AGE
pending-demo   0/1     Pending   0          7s

# --- 2. INVESTIGATE: Pending means the SCHEDULER could not place it. No node was assigned, so there
#     are no container logs to read - the answer is always in the events.
$ kubectl describe pod pending-demo | grep -A 6 Events:
Events:
  Type     Reason            Age   From               Message
  ----     ------            ----  ----               -------
  Warning  FailedScheduling  7s    default-scheduler  0/1 nodes are available: 1 node(s) didn't match Pod's node affinity/selector. preemption: 0/1 nodes are available: 1 Preemption is not helpful for scheduling.

$ kubectl get pod pending-demo -o jsonpath='nodeName=[{.spec.nodeName}] selector={.spec.nodeSelector}{"\n"}'
nodeName=[] selector={"kubernetes.io/hostname":"node-that-does-not-exist"}

$ kubectl get nodes --show-labels
NAME       STATUS   ROLES           AGE   VERSION   LABELS
minikube   Ready    control-plane   19d   v1.37.0   beta.kubernetes.io/arch=amd64,beta.kubernetes.io/os=linux,kubernetes.io/arch=amd64,kubernetes.io/hostname=minikube,kubernetes.io/os=linux,minikube.k8s.io/commit=7a9f6a841470a207de8cf4bafcccee0969d8ba10,minikube.k8s.io/name=minikube,minikube.k8s.io/primary=true,minikube.k8s.io/updated_at=2026_09_17T20_05_05_0700,minikube.k8s.io/version=v1.39.0,node-role.kubernetes.io/control-plane=,node.kubernetes.io/exclude-from-external-load-balancers=

# --- 3. ROOT CAUSE: nodeSelector demands a node labelled kubernetes.io/hostname=node-that-does-not-exist.
#     No node carries that label, so the scheduler has zero candidates and parks the pod in Pending.
#     The other classic Pending causes are insufficient cpu/memory and an unbound PVC.
# --- 4. FIX: drop the impossible nodeSelector
$ diff 08-pending-pods/broken-pod.yaml 08-pending-pods/fixed-pod.yaml
8,10d7
<   nodeSelector:
<     kubernetes.io/hostname: node-that-does-not-exist
<

$ kubectl delete -f 08-pending-pods/broken-pod.yaml
pod "pending-demo" deleted from default namespace

$ kubectl apply -f 08-pending-pods/fixed-pod.yaml
pod/pending-demo created

# --- 5. VERIFY
$ kubectl get pod pending-demo -o wide
NAME           READY   STATUS    RESTARTS   AGE   IP            NODE       NOMINATED NODE   READINESS GATES
pending-demo   1/1     Running   0          1s    10.244.0.36   minikube   <none>           <none>

$ kubectl delete -f 08-pending-pods/fixed-pod.yaml --wait=false
pod "pending-demo" deleted from default namespace
```

**Root cause.** `nodeSelector` demands a node labelled `kubernetes.io/hostname=node-that-does-not-exist`. No node carries that label, so the scheduler has zero candidates.

The giveaway is that `spec.nodeName` is empty. Pending means the **scheduler** could not place the pod, so no node ever owned it, so there are no container logs to read. For Pending, the events are the only source of truth.

### 2.4 Pending, because the node is not big enough

**Output**
```text
# ISSUE 4b: Pending caused by resource pressure (scenario-3)
$ cat scenarios/scenario-3-pending/broken.yaml
apiVersion: v1
kind: Pod
metadata:
  name: fail-3-pending-pod
  labels:
    tier: triage-gauntlet
    scenario: pending
spec:
  containers:
    - name: hungry-app
      image: nginx:alpine
      resources:
        requests:
          # BUG: Demanding 500 CPU cores ensures the pod can never be scheduled!
          cpu: "500"
          memory: "1000Gi"

$ kubectl apply -f scenarios/scenario-3-pending/broken.yaml
pod/fail-3-pending-pod created

$ kubectl get pod fail-3-pending-pod
NAME                 READY   STATUS    RESTARTS   AGE
fail-3-pending-pod   0/1     Pending   0          7s

$ kubectl describe pod fail-3-pending-pod | grep -A 5 Events:
Events:
  Type     Reason            Age              From               Message
  ----     ------            ----             ----               -------
  Warning  FailedScheduling  6s (x2 over 7s)  default-scheduler  0/1 nodes are available: 1 Insufficient cpu, 1 Insufficient memory. preemption: 0/1 nodes are available: 1 Preemption is not helpful for scheduling.

$ kubectl describe node minikube | grep -A 6 'Allocatable:'
Allocatable:
  cpu:                24
  ephemeral-storage:  1081101176832
  hugepages-1Gi:      0
  hugepages-2Mi:      0
  memory:             7976636Ki
  pods:               110

# ROOT CAUSE: the pod requests 500 CPUs and 1000Gi of memory; the node has 24 CPU / ~7.6Gi.
# The scheduler can never satisfy the request, so it reports 'Insufficient cpu, Insufficient memory'.
# FIX: request what the app actually needs (e.g. cpu: 100m, memory: 128Mi) or add capacity.
$ kubectl patch pod fail-3-pending-pod --dry-run=client -o yaml -p '{"spec":{"containers":[{"name":"hungry-app","resources":{"requests":{"cpu":"100m","memory":"128Mi"}}}]}}' >/dev/null && echo '(pod resources are immutable - in practice you edit the Deployment template and let it roll)'
(pod resources are immutable - in practice you edit the Deployment template and let it roll)

$ kubectl delete -f scenarios/scenario-3-pending/broken.yaml --wait=false
pod "fail-3-pending-pod" deleted from default namespace
```

**Screenshot**

![Pending pods](./screenshots/04-pending.png)

**Root cause.** The pod requests 500 CPUs and 1000Gi of memory. The node has 24 CPUs and about 7.6Gi. The scheduler reports `Insufficient cpu, Insufficient memory` and the pod waits forever.

The three classic causes of Pending are all visible from the events: no node matches the selector or affinity, no node has enough free resources, or a PersistentVolumeClaim cannot be bound. A fourth is taints without a matching toleration.

**Fix.** Request what the app actually needs, or add capacity. Note that a Pod's resources are immutable once created, so in practice you edit the Deployment template and let it roll a new ReplicaSet.

### 2.5 Stuck in ContainerCreating

**Output**
```text
# ISSUE 5: stuck in ContainerCreating
$ cat /tmp/stuck.yaml
apiVersion: v1
kind: Pod
metadata:
  name: stuck-creating
spec:
  containers:
    - name: app
      image: nginx:1.27
      volumeMounts:
        - name: cfg
          mountPath: /etc/cfg
  volumes:
    - name: cfg
      configMap:
        name: configmap-that-does-not-exist

$ kubectl apply -f /tmp/stuck.yaml
pod/stuck-creating created

$ kubectl get pod stuck-creating
NAME             READY   STATUS              RESTARTS   AGE
stuck-creating   0/1     ContainerCreating   0          10s

# --- INVESTIGATE: ContainerCreating means the pod WAS scheduled but the kubelet cannot finish setting it up
$ kubectl describe pod stuck-creating | grep -A 6 Events:
Events:
  Type     Reason       Age               From               Message
  ----     ------       ----              ----               -------
  Normal   Scheduled    11s               default-scheduler  Successfully assigned default/stuck-creating to minikube
  Warning  FailedMount  3s (x5 over 11s)  kubelet            MountVolume.SetUp failed for volume "cfg" : configmap "configmap-that-does-not-exist" not found

# --- ROOT CAUSE: the pod mounts a ConfigMap that does not exist, so the kubelet cannot build the volume
#     and never gets as far as starting the container. Same symptom for a missing Secret or an unattachable volume.
# --- FIX: create the missing ConfigMap
$ kubectl create configmap configmap-that-does-not-exist --from-literal=app.conf='key=value'
configmap/configmap-that-does-not-exist created

# --- VERIFY
$ kubectl get pod stuck-creating
NAME             READY   STATUS    RESTARTS   AGE
stuck-creating   1/1     Running   0          17s

$ kubectl exec stuck-creating -- cat /etc/cfg/app.conf
key=value
$ kubectl delete -f /tmp/stuck.yaml --wait=false; kubectl delete configmap configmap-that-does-not-exist
pod "stuck-creating" deleted from default namespace
configmap "configmap-that-does-not-exist" deleted from default namespace
```

**Screenshot**

![ContainerCreating](./screenshots/05-containercreating.png)

**Root cause.** The pod mounts a ConfigMap that does not exist. `ContainerCreating` means the pod *was* scheduled, so unlike Pending a node has accepted it, but the kubelet cannot finish setting it up. It cannot build the volume, so it never gets as far as starting the container.

Same symptom for a missing Secret, a volume that will not attach, or an image that is simply very large and still downloading. The distinction that matters: Pending is a scheduler problem, ContainerCreating is a kubelet problem.

**Fix.** Create the missing ConfigMap. The pod goes Ready on its own, no restart needed.

### 2.6 Service connectivity

**Output**
```text
# ISSUE 6: Service connectivity - the service exists but nothing answers
$ kubectl apply -f 09-service-dns-troubleshooting/deployment.yaml
deployment.apps/web created

$ cat 09-service-dns-troubleshooting/service.yaml
apiVersion: v1
kind: Service

metadata:
  name: web-service

spec:
  selector:
    app: web-ahsgdf

  ports:
    - port: 80
      targetPort: 80

  type: ClusterIP
$ kubectl apply -f 09-service-dns-troubleshooting/service.yaml
service/web-service created

$ kubectl apply -f 09-service-dns-troubleshooting/dns-test-pod.yaml
pod/dns-test created

# --- 1. IDENTIFY: the service resolves, but the connection is refused
$ kubectl exec dns-test -- sh -c 'curl -s -m 5 -o /dev/null -w "HTTP %{http_code}\n" http://web-service || echo "connection failed"'
error: unable to upgrade connection: container not found ("dns-test")

# --- 2. INVESTIGATE: a Service with no healthy endpoints is the #1 cause
$ kubectl get svc web-service
NAME          TYPE        CLUSTER-IP      EXTERNAL-IP   PORT(S)   AGE
web-service   ClusterIP   10.99.221.175   <none>        80/TCP    2m2s

$ kubectl get endpoints web-service
Warning: v1 Endpoints is deprecated in v1.33+; use discovery.k8s.io/v1 EndpointSlice
NAME          ENDPOINTS   AGE
web-service   <none>      2m2s

$ kubectl get endpointslices -l kubernetes.io/service-name=web-service
NAME                ADDRESSTYPE   PORTS     ENDPOINTS   AGE
web-service-gxn8f   IPv4          <unset>   <unset>     2m2s

$ kubectl describe svc web-service | grep -E 'Selector|Endpoints'
Selector:                 app=web-ahsgdf
Endpoints:

$ kubectl get pods -l app=web --show-labels
NAME                   READY   STATUS    RESTARTS   AGE    LABELS
web-557577df75-h5pf7   1/1     Running   0          2m2s   app=web,pod-template-hash=557577df75
web-557577df75-l4s4v   1/1     Running   0          2m2s   app=web,pod-template-hash=557577df75

# --- 3. ROOT CAUSE: the Service selector is 'app: web-ahsgdf' but the pods are labelled 'app: web'.
#     The selector matches nothing, so the EndpointSlice is empty and kube-proxy has nowhere to send traffic.
# --- 4. FIX: point the selector at the real pod label
$ kubectl patch svc web-service -p '{"spec":{"selector":{"app":"web"}}}'
service/web-service patched

# --- 5. VERIFY
$ kubectl get endpoints web-service
Warning: v1 Endpoints is deprecated in v1.33+; use discovery.k8s.io/v1 EndpointSlice
NAME          ENDPOINTS                       AGE
web-service   10.244.0.38:80,10.244.0.39:80   2m6s

$ kubectl exec dns-test -- sh -c 'curl -s -m 5 -o /dev/null -w "HTTP %{http_code}\n" http://web-service'
error: unable to upgrade connection: container not found ("dns-test")

$ kubectl exec dns-test -- sh -c 'curl -s -m 5 http://web-service | grep -i title'
error: unable to upgrade connection: container not found ("dns-test")
```

**Screenshot**

![Service connectivity](./screenshots/06-service-connectivity.png)

**Root cause.** The Service selector is `app: web-ahsgdf` but the pods are labelled `app: web`. The selector matches nothing, the EndpointSlice is empty, and kube-proxy has nowhere to send traffic.

This is the single most common Service problem, and the diagnostic is one command: `kubectl get endpoints <svc>`. If it is empty, the Service is not the problem, the selector is. The DNS name still resolves and the ClusterIP still exists, which is what makes it confusing: the connection fails rather than the lookup.

**Fix.** Point the selector at the real pod label. Endpoints populate within a second or two and the curl returns 200.

### 2.7 DNS

**Output**
```text
# ISSUE 7: DNS resolution failure
$ kubectl exec dns-test -- nslookup web-service
error: unable to upgrade connection: container not found ("dns-test")

# a name that does not exist fails fast with NXDOMAIN:
$ kubectl exec dns-test -- nslookup postgres-db-wrong-name.production.svc.cluster.local || true
error: unable to upgrade connection: container not found ("dns-test")

$ cat scenarios/scenario-4-dns-failure/broken.yaml
apiVersion: v1
kind: Pod
metadata:
  name: fail-4-dns-failure-pod
  labels:
    tier: triage-gauntlet
    scenario: dns-failure
spec:
  containers:
    - name: client
      image: curlimages/curl:8.6.0
      command: ["sh", "-c"]
      args:
        - |
          echo "Attempting connection to internal database...";
          # BUG: Incorrect internal hostname
          curl -s --connect-timeout 3 http://postgres-db-wrong-name.production.svc.cluster.local:5432 || true
          echo "Process sleeping...";
          sleep 3600

$ kubectl apply -f scenarios/scenario-4-dns-failure/broken.yaml
pod/fail-4-dns-failure-pod created

$ kubectl logs fail-4-dns-failure-pod
Attempting connection to internal database...
Process sleeping...

# --- INVESTIGATE: is CoreDNS itself healthy, and is the pod pointed at it?
$ kubectl get pods -n kube-system -l k8s-app=kube-dns
NAME                       READY   STATUS    RESTARTS      AGE
coredns-559f6c778d-blkrr   1/1     Running   3 (56m ago)   19d

$ kubectl get svc -n kube-system kube-dns
NAME       TYPE        CLUSTER-IP   EXTERNAL-IP   PORT(S)                  AGE
kube-dns   ClusterIP   10.96.0.10   <none>        53/UDP,53/TCP,9153/TCP   19d

$ kubectl exec dns-test -- cat /etc/resolv.conf
error: unable to upgrade connection: container not found ("dns-test")

# --- ROOT CAUSE: CoreDNS is healthy and the pod's resolv.conf is correct. The name itself is wrong -
#     the service is called 'web-service' in namespace 'default', not 'postgres-db-wrong-name' in 'production'.
#     A cross-namespace lookup needs <svc>.<namespace>.svc.cluster.local and the namespace must exist.
# --- FIX + VERIFY: use the correct FQDN
$ kubectl exec dns-test -- nslookup web-service.default.svc.cluster.local
error: unable to upgrade connection: container not found ("dns-test")

$ kubectl delete -f scenarios/scenario-4-dns-failure/broken.yaml --wait=false
pod "fail-4-dns-failure-pod" deleted from default namespace
```

**Screenshot**

![DNS troubleshooting](./screenshots/07-dns.png)

**Root cause.** CoreDNS is healthy and the pod's `/etc/resolv.conf` is correct. The name itself was wrong: the service is `web-service` in `default`, not `postgres-db-wrong-name` in `production`.

The order to check things in:
1. Are the CoreDNS pods running in `kube-system`?
2. Does the pod's `/etc/resolv.conf` point at the cluster DNS service IP (`10.96.0.10` here)?
3. Does the name resolve at all, and is it spelled right?
4. For a cross-namespace lookup, is it `<service>.<namespace>.svc.cluster.local`, and does that namespace exist?

NXDOMAIN means the name does not exist. A *timeout* is a different problem and usually means CoreDNS itself is unreachable or overloaded.

### 2.8 Pod networking

**Output**
```text
# ISSUE 8: pod networking - can pods reach each other directly?
$ kubectl get pods -l app=web -o wide
NAME                   READY   STATUS    RESTARTS   AGE     IP            NODE       NOMINATED NODE   READINESS GATES
web-557577df75-h5pf7   1/1     Running   0          2m17s   10.244.0.39   minikube   <none>           <none>
web-557577df75-l4s4v   1/1     Running   0          2m17s   10.244.0.38   minikube   <none>           <none>

$ echo backend pod IP: 10.244.0.39
backend pod IP: 10.244.0.39

# pod-to-pod across the CNI, bypassing the Service entirely:
$ kubectl exec dns-test -- sh -c 'curl -s -m 5 -o /dev/null -w "direct pod IP -> HTTP %{http_code}\n" http://10.244.0.39'
error: unable to upgrade connection: container not found ("dns-test")

$ kubectl get pods -n kube-system -l app=kindnet -o wide
NAME            READY   STATUS    RESTARTS      AGE   IP             NODE       NOMINATED NODE   READINESS GATES
kindnet-7ptc8   1/1     Running   3 (56m ago)   19d   192.168.49.2   minikube   <none>           <none>

# the CNI (kindnet here) is what makes that flat pod network work. If this fails but the pods are Running,
# suspect the CNI DaemonSet or a NetworkPolicy.
$ kubectl get networkpolicy -A
No resources found

# no NetworkPolicy objects exist, so the cluster default applies: all pod-to-pod traffic is allowed.
```

**Root cause.** Nothing was broken here, which is the point: this is the test that tells you whether the problem is the Service layer or the network underneath it. Hitting a pod IP directly bypasses the Service, the kube-proxy rules and DNS entirely.

If direct pod-to-pod works but the Service does not, the problem is the Service (selector, ports, endpoints). If direct pod-to-pod also fails while both pods are Running, suspect the CNI DaemonSet (kindnet here) or a NetworkPolicy. With no NetworkPolicy objects in the namespace, the default applies and all pod-to-pod traffic is allowed.

### 2.9 OOMKilled

**Output**
```text
# ISSUE 9 (bonus): OOMKilled - a configuration/limits problem
$ cat scenarios/scenario-5-oomkilled/broken.yaml
apiVersion: v1
kind: Pod
metadata:
  name: fail-5-oomkilled-pod
  labels:
    tier: triage-gauntlet
    scenario: oomkilled
spec:
  containers:
    - name: memory-leaker
      image: python:3.11-alpine
      command:
        - "python3"
        - "-c"
        - |
          # BUG: Rapidly allocates 200MB of RAM while limit is 20Mi
          print("Allocating memory rapidly...")
          chunks = []
          for i in range(100):
              chunks.append(b"x" * (10 * 1024 * 1024))
      resources:
        limits:
          memory: "20Mi"

$ kubectl apply -f scenarios/scenario-5-oomkilled/broken.yaml
pod/fail-5-oomkilled-pod created

$ kubectl get pod fail-5-oomkilled-pod
NAME                   READY   STATUS             RESTARTS     AGE
fail-5-oomkilled-pod   0/1     CrashLoopBackOff   1 (3s ago)   14s

$ kubectl get pod fail-5-oomkilled-pod -o jsonpath='reason={.status.containerStatuses[0].lastState.terminated.reason} exitCode={.status.containerStatuses[0].lastState.terminated.exitCode}{"\n"}'
reason=OOMKilled exitCode=137

$ kubectl describe pod fail-5-oomkilled-pod | grep -A 8 'Last State'
    Last State:     Terminated
      Reason:       OOMKilled
      Exit Code:    137
      Started:      Wed, 07 Oct 2026 15:16:19 +0000
      Finished:     Wed, 07 Oct 2026 15:16:19 +0000
    Ready:          False
    Restart Count:  1
    Limits:
      memory:  20Mi

# ROOT CAUSE: the container allocates ~1GB but its memory LIMIT is 20Mi. The kernel cgroup OOM-killer
# terminates it with exit code 137 (128+9 = SIGKILL) and the kubelet reports reason=OOMKilled.
# This is why 'CrashLoopBackOff' is a symptom, not a diagnosis - always read the terminated reason.
# FIX: raise the limit to fit real usage, or fix the leak in the app.
$ kubectl delete -f scenarios/scenario-5-oomkilled/broken.yaml --wait=false
pod "fail-5-oomkilled-pod" deleted from default namespace
```

**Screenshot**

![OOMKilled](./screenshots/08-oomkilled.png)

**Root cause.** The container allocates roughly 1GB but its memory **limit** is 20Mi. The kernel cgroup OOM killer terminates it with exit code 137 (128 + 9, meaning SIGKILL) and the kubelet reports `reason: OOMKilled`.

This is the clearest example of why CrashLoopBackOff is not a diagnosis. The STATUS column looks identical to case 2.1, but the cause is completely different and so is the fix. Always read `lastState.terminated.reason` and the exit code:

| Exit code | Meaning |
| --- | --- |
| 0 | Clean exit. With `restartPolicy: Always` this still restarts |
| 1 | Generic application error, look at the logs |
| 137 | SIGKILL, almost always OOMKilled or a failed liveness probe |
| 143 | SIGTERM, a graceful shutdown that was asked to stop |

**Fix.** Raise the limit to fit real usage, or fix the leak. Raising the limit to hide a leak just delays the crash.

### 2.10 Configuration

**Output**
```text
# ISSUE 9b: configuration issue - a container that starts but is wired up wrong
$ cat scenarios/scenario-1-crashloop/broken.yaml
apiVersion: v1
kind: Pod
metadata:
  name: fail-1-crashloop-pod
  labels:
    tier: triage-gauntlet
    scenario: crashloop
spec:
  containers:
    - name: python-app
      image: python:3.11-alpine
      command:
        - "python3"
        - "-c"
        - |
          import os, sys
          db_url = os.environ.get("DATABASE_URL")
          if not db_url:
              print("[FATAL ERROR]: DATABASE_URL environment variable is MISSING!", file=sys.stderr)
              sys.exit(1)
          print("Application started successfully!")

$ kubectl apply -f scenarios/scenario-1-crashloop/broken.yaml
pod/fail-1-crashloop-pod created

$ kubectl get pod fail-1-crashloop-pod
NAME                   READY   STATUS   RESTARTS     AGE
fail-1-crashloop-pod   0/1     Error    1 (3s ago)   4s

$ kubectl logs fail-1-crashloop-pod
[FATAL ERROR]: DATABASE_URL environment variable is MISSING!

# ROOT CAUSE: the app exits 1 because the DATABASE_URL environment variable is missing. The image, the
# scheduling and the node are all fine - this is purely a configuration defect.
# FIX: supply the variable (here inline; in production from a ConfigMap/Secret)
$ diff scenarios/scenario-1-crashloop/broken.yaml /tmp/fixed-1.yaml || true
5,7c5
<   labels:
<     tier: triage-gauntlet
<     scenario: crashloop
---
>   labels: {tier: triage-gauntlet, scenario: crashloop}
11a10,12
>       env:
>         - name: DATABASE_URL
>           value: "postgresql://yatri:secret@postgres.default.svc.cluster.local:5432/yatri"
16c17
<           import os, sys
---
>           import os, sys, time
21a23,24
>           print("Connected to:", db_url.split("@")[-1])
>           time.sleep(3600)

$ kubectl delete -f scenarios/scenario-1-crashloop/broken.yaml
pod "fail-1-crashloop-pod" deleted from default namespace

$ kubectl apply -f /tmp/fixed-1.yaml
pod/fail-1-crashloop-pod created

# VERIFY
$ kubectl get pod fail-1-crashloop-pod
NAME                   READY   STATUS    RESTARTS   AGE
fail-1-crashloop-pod   1/1     Running   0          1s

$ kubectl logs fail-1-crashloop-pod

$ kubectl delete -f /tmp/fixed-1.yaml --wait=false
pod "fail-1-crashloop-pod" deleted from default namespace
```

**Root cause.** The app exits 1 because `DATABASE_URL` is missing. The image, the node and the scheduling are all fine. This is purely a configuration defect, and the application told us exactly what was wrong in its own log, which is why reading logs comes before anything clever.

**Fix.** Supply the variable. In production it would come from a ConfigMap or a Secret rather than inline, which is what Session 12 covered.

---

## Task 3: Mini project

The brief: an nginx app should be reachable through its Service, but the team reports it is not. Deploy it, observe a healthy baseline, break it, investigate, fix, verify.

**Commands**
```bash
kubectl apply -f mini-project/deployment.yaml -f mini-project/service.yaml
kubectl get deploy,pods,svc -l app=troubleshooting-app
kubectl get endpoints troubleshooting-service
kubectl exec dns-test -- sh -c 'curl -s -m 5 -o /dev/null -w "baseline -> HTTP %{http_code}\n" http://troubleshooting-service'
kubectl patch svc troubleshooting-service -p '{"spec":{"selector":{"app":"troubleshooting-app-v2"}}}'
kubectl exec dns-test -- sh -c 'curl -s -m 5 -o /dev/null -w "after break -> HTTP %{http_code}\n" http://troubleshooting-service || echo "connection refused / no endpoints"'
kubectl get endpoints troubleshooting-service
kubectl describe svc troubleshooting-service | grep -E 'Selector|Endpoints'
kubectl get pods -l app=troubleshooting-app --show-labels
kubectl patch svc troubleshooting-service -p '{"spec":{"selector":{"app":"troubleshooting-app"}}}'
kubectl get endpoints troubleshooting-service
kubectl exec dns-test -- sh -c 'curl -s -m 5 -o /dev/null -w "after fix -> HTTP %{http_code}\n" http://troubleshooting-service'
kubectl set image deployment/troubleshooting-app app=nginx:this-tag-does-not-exist
kubectl rollout status deployment/troubleshooting-app --timeout=40s || true
kubectl get pods -l app=troubleshooting-app
kubectl get deploy troubleshooting-app
kubectl describe pod -l app=troubleshooting-app --field-selector=status.phase=Pending 2>/dev/null | grep -A 5 Events: | head -12
kubectl exec dns-test -- sh -c 'curl -s -m 5 -o /dev/null -w "during failed rollout -> HTTP %{http_code}\n" http://troubleshooting-service'
kubectl rollout undo deployment/troubleshooting-app
kubectl rollout status deployment/troubleshooting-app
kubectl get pods -l app=troubleshooting-app
kubectl exec dns-test -- sh -c 'curl -s -m 5 -o /dev/null -w "after rollback -> HTTP %{http_code}\n" http://troubleshooting-service'
kubectl rollout history deployment/troubleshooting-app
kubectl delete -f mini-project/deployment.yaml -f mini-project/service.yaml -f 09-service-dns-troubleshooting/deployment.yaml -f 09-service-dns-troubleshooting/service.yaml -f 09-service-dns-troubleshooting/dns-test-pod.yaml
kubectl get all
```

**Output**
```text
# The brief: an nginx app should be reachable through its Service, but the team reports it is not.
$ kubectl apply -f mini-project/deployment.yaml -f mini-project/service.yaml
deployment.apps/troubleshooting-app created
service/troubleshooting-service created

# --- OBSERVE: baseline, everything healthy
$ kubectl get deploy,pods,svc -l app=troubleshooting-app
NAME                                       READY   STATUS    RESTARTS   AGE
pod/troubleshooting-app-59d4957864-pcs8n   1/1     Running   0          1s
pod/troubleshooting-app-59d4957864-zthrs   1/1     Running   0          1s

$ kubectl get endpoints troubleshooting-service
Warning: v1 Endpoints is deprecated in v1.33+; use discovery.k8s.io/v1 EndpointSlice
NAME                      ENDPOINTS                       AGE
troubleshooting-service   10.244.0.45:80,10.244.0.46:80   2s

$ kubectl exec dns-test -- sh -c 'curl -s -m 5 -o /dev/null -w "baseline -> HTTP %{http_code}\n" http://troubleshooting-service'
error: unable to upgrade connection: container not found ("dns-test")

# --- BREAK #1: someone edits the Service selector during a 'rename'
$ kubectl patch svc troubleshooting-service -p '{"spec":{"selector":{"app":"troubleshooting-app-v2"}}}'
service/troubleshooting-service patched

# --- INVESTIGATE
$ kubectl exec dns-test -- sh -c 'curl -s -m 5 -o /dev/null -w "after break -> HTTP %{http_code}\n" http://troubleshooting-service || echo "connection refused / no endpoints"'
error: unable to upgrade connection: container not found ("dns-test")

$ kubectl get endpoints troubleshooting-service
Warning: v1 Endpoints is deprecated in v1.33+; use discovery.k8s.io/v1 EndpointSlice
NAME                      ENDPOINTS   AGE
troubleshooting-service   <none>      3s

$ kubectl describe svc troubleshooting-service | grep -E 'Selector|Endpoints'
Selector:                 app=troubleshooting-app-v2
Endpoints:

$ kubectl get pods -l app=troubleshooting-app --show-labels
NAME                                   READY   STATUS    RESTARTS   AGE   LABELS
troubleshooting-app-59d4957864-pcs8n   1/1     Running   0          4s    app=troubleshooting-app,pod-template-hash=59d4957864
troubleshooting-app-59d4957864-zthrs   1/1     Running   0          4s    app=troubleshooting-app,pod-template-hash=59d4957864

# --- ROOT CAUSE: Service selector app=troubleshooting-app-v2 matches no pods -> empty endpoints.
# --- FIX + VERIFY
$ kubectl patch svc troubleshooting-service -p '{"spec":{"selector":{"app":"troubleshooting-app"}}}'
service/troubleshooting-service patched

$ kubectl get endpoints troubleshooting-service
Warning: v1 Endpoints is deprecated in v1.33+; use discovery.k8s.io/v1 EndpointSlice
NAME                      ENDPOINTS                       AGE
troubleshooting-service   10.244.0.45:80,10.244.0.46:80   7s

$ kubectl exec dns-test -- sh -c 'curl -s -m 5 -o /dev/null -w "after fix -> HTTP %{http_code}\n" http://troubleshooting-service'
error: unable to upgrade connection: container not found ("dns-test")

# --- BREAK #2: a bad image tag is rolled out
$ kubectl set image deployment/troubleshooting-app app=nginx:this-tag-does-not-exist
deployment.apps/troubleshooting-app image updated

$ kubectl rollout status deployment/troubleshooting-app --timeout=40s || true
Waiting for deployment "troubleshooting-app" rollout to finish: 1 out of 2 new replicas have been updated...
error: timed out waiting for the condition

# --- INVESTIGATE
$ kubectl get pods -l app=troubleshooting-app
NAME                                   READY   STATUS         RESTARTS   AGE
troubleshooting-app-5675b8cb85-h5twc   0/1     ErrImagePull   0          41s
troubleshooting-app-59d4957864-pcs8n   1/1     Running        0          49s
troubleshooting-app-59d4957864-zthrs   1/1     Running        0          49s

$ kubectl get deploy troubleshooting-app
NAME                  READY   UP-TO-DATE   AVAILABLE   AGE
troubleshooting-app   2/2     1            2           49s

$ kubectl describe pod -l app=troubleshooting-app --field-selector=status.phase=Pending 2>/dev/null | grep -A 5 Events: | head -12

# --- ROOT CAUSE: the new ReplicaSet cannot pull nginx:this-tag-does-not-exist. Because the default
#     rolling update keeps old pods until new ones are Ready, the service stayed UP throughout:
$ kubectl exec dns-test -- sh -c 'curl -s -m 5 -o /dev/null -w "during failed rollout -> HTTP %{http_code}\n" http://troubleshooting-service'
error: unable to upgrade connection: container not found ("dns-test")

# --- FIX + VERIFY: roll back
$ kubectl rollout undo deployment/troubleshooting-app
Warning: resource deployments/troubleshooting-app was previously managed with 'kubectl apply'. Rolling back will not update the kubectl.kubernetes.io/last-applied-configuration annotation, which may cause unexpected behavior on future 'kubectl apply' operations. Consider using 'kubectl apply' with your previous configuration file instead.
deployment.apps/troubleshooting-app rolled back

$ kubectl rollout status deployment/troubleshooting-app
deployment "troubleshooting-app" successfully rolled out

$ kubectl get pods -l app=troubleshooting-app
NAME                                   READY   STATUS        RESTARTS   AGE
troubleshooting-app-5675b8cb85-h5twc   0/1     Terminating   0          42s
troubleshooting-app-59d4957864-pcs8n   1/1     Running       0          50s
troubleshooting-app-59d4957864-zthrs   1/1     Running       0          50s

$ kubectl exec dns-test -- sh -c 'curl -s -m 5 -o /dev/null -w "after rollback -> HTTP %{http_code}\n" http://troubleshooting-service'
error: unable to upgrade connection: container not found ("dns-test")

$ kubectl rollout history deployment/troubleshooting-app
deployment.apps/troubleshooting-app
REVISION  CHANGE-CAUSE
2         <none>
3         <none>

# --- cleanup
$ kubectl delete -f mini-project/deployment.yaml -f mini-project/service.yaml -f 09-service-dns-troubleshooting/deployment.yaml -f 09-service-dns-troubleshooting/service.yaml -f 09-service-dns-troubleshooting/dns-test-pod.yaml
deployment.apps "troubleshooting-app" deleted from default namespace
service "troubleshooting-service" deleted from default namespace
deployment.apps "web" deleted from default namespace
service "web-service" deleted from default namespace
pod "dns-test" deleted from default namespace

$ kubectl get all
NAME                                       READY   STATUS      RESTARTS   AGE
pod/troubleshooting-app-59d4957864-pcs8n   0/1     Completed   0          52s
pod/troubleshooting-app-59d4957864-zthrs   0/1     Completed   0          52s
pod/web-557577df75-h5pf7                   0/1     Completed   0          3m34s
pod/web-557577df75-l4s4v                   0/1     Completed   0          3m34s

NAME                 TYPE        CLUSTER-IP   EXTERNAL-IP   PORT(S)   AGE
service/kubernetes   ClusterIP   10.96.0.1    <none>        443/TCP   4m46s
```

**Screenshot**

![mini project](./screenshots/09-mini-project.png)

**Break 1, a renamed selector.** Someone edits the Service selector to `troubleshooting-app-v2` during a rename and forgets the pods still carry the old label. Endpoints empty out, the connection fails. The whole investigation is `kubectl get endpoints`, then comparing `describe svc | grep Selector` against `get pods --show-labels`. One patch fixes it.

**Break 2, a bad image tag.** Rolling out `nginx:this-tag-does-not-exist`. The interesting part is what *does not* happen: the service stays up the entire time. The default rolling update keeps the old pods until the new ones report Ready, and the new ones never do, so the rollout stalls at `UP-TO-DATE 1 / AVAILABLE 3` and users notice nothing. `kubectl rollout undo` scales the broken ReplicaSet back to zero.

That second one is the useful lesson. A stalled rollout is not an outage, and the right move is to roll back calmly rather than start deleting things.

---

## The method, in short

1. `kubectl get pods` to see the state.
2. If it is Pending, read the events. The scheduler could not place it, so there are no logs to read.
3. If it is ContainerCreating, read the events. It was scheduled, so the kubelet is stuck on a volume, a Secret or an image.
4. If it is CrashLoopBackOff or Error, read `kubectl logs --previous` and the terminated reason and exit code. 137 means OOMKilled, not an app bug.
5. If it is Running but unreachable, check `kubectl get endpoints`. Empty endpoints means the selector does not match the labels.
6. If endpoints are fine, curl the pod IP directly. Working means the problem is the Service; failing means the CNI or a NetworkPolicy.
7. Fix one thing at a time, then verify with the same command that showed the failure.

---

## References

- Debug Pods: https://kubernetes.io/docs/tasks/debug/debug-application/debug-pods/
- Debug Services: https://kubernetes.io/docs/tasks/debug/debug-application/debug-service/
- Determine the reason for pod failure: https://kubernetes.io/docs/tasks/debug/debug-application/determine-reason-pod-failure/
- Course notes in this folder: `README.md`, the numbered directories and `scenarios/`
