# Phase 0 麒麟 VM 现状证据（2026-08-24）

- **project**: kylin-os-agent-memory
- **task**: Phase 0 协议对齐 ALIGN-005 socket 现状调查
- **branch**: feat/d4-phase0-ipc-alignment
- **commit_sha**: ec3a91e5858f1e7fe210a9850e5c9d54fdc9b109
- **result**: INVESTIGATION_ONLY（仅环境现状调查，非当前 HEAD 的 L2 执行证据）
- **limitations**: 本次收集发生在目标 HEAD 代码执行之前，仅记录环境中已存在的 socket/进程现状，不构成 PR#57 的 L2 验证证据；servicekey 等敏感值已脱敏（REDACTED）。

## system_identity
```
# exit=0
Linux kylin-agent-pc 6.6.0-76-generic #86r2-KYLINOS SMP PREEMPT_DYNAMIC Tue Aug  4 06:44:37 UTC 2026 x86_64 x86_64 x86_64 GNU/Linux
---
uid=1000(kylin-agent) gid=1000(kylin-agent) 组=1000(kylin-agent),4(adm),24(cdrom),27(sudo),30(dip),46(plugdev),100(users),114(lpadmin),987(vboxsf),989(sambashare)
---
XDG_RUNTIME_DIR=/run/user/1000
```

## os_release
```
# exit=0
[dist]
name=Kylin-Desktop
milestone=V11
arch=x86_64
beta=False
time=2026-02-12 12:04:58
dist_id=Kylin-Desktop-V11-2603-Release-20260228-X86_64-2026-02-12 12:04:58

[servicekey]
key=REDACTED

[os]
to=
term=2027-05-29
```

## frozen_socket_path
```
# exit=0
XDG=/run/user/1000
总计 0
drwxr-xr-x  2 kylin-agent kylin-agent  60  8月24日 15:36 .
drwx------ 13 kylin-agent kylin-agent 400  8月22日 18:50 ..
srwxrwxr-x  1 kylin-agent kylin-agent   0  8月24日 15:36 embedding.sock
ls: 无法访问 '/run/user/1000/kylin-memory/memory.sock': 没有那个文件或目录
NO_MEMORY_SOCK
```

## echo_systemd_path
```
# exit=0
ls: 无法访问 '/run/kylin-memory-echo': 没有那个文件或目录
NOT_FOUND
ls: 无法访问 '/run/kylin-memory-echo/echo.sock': 没有那个文件或目录
NO_SOCK
```

## echo_dev_path
```
# exit=0
ls: 无法访问 '/tmp/kylin-memory-echo': 没有那个文件或目录
NOT_FOUND
ls: 无法访问 '/tmp/kylin-memory-echo/echo.sock': 没有那个文件或目录
NO_SOCK
```

## embedding_path
```
# exit=0
ls: 无法访问 '/tmp/kylin-memory-embed.sock': 没有那个文件或目录
NOT_FOUND
```

## kma_path
```
# exit=0
ls: 无法访问 '/tmp/kylin-memory-service.sock': 没有那个文件或目录
NOT_FOUND
```

## all_sockets
```
# exit=0
u_str LISTEN 0      50                                                                                        /var/tmp/kylin-daq-daemon 10777              * 0                                                                         
u_str LISTEN 0      8                                                                           /run/user/1000/kylin-memory/memory.sock 18459              * 0    users:(("python",pid=3107,fd=7))                                     
u_str LISTEN 0      128                                                                                        /run/user/1000/wayland-0 18702              * 0    users:(("kylin-wlcom",pid=4868,fd=34),("kylin-wlcom",pid=4868,fd=21))
u_str LISTEN 0      50                                                   /home/kylin-agent/.local/share/Kingsoft/daemon/wps-daemon-port 57859              * 0    users:(("wpsd",pid=10567,fd=6))                                      
u_str LISTEN 0      4096                                                                          /tmp/kylin-ai-vector-engine-1000.sock 13644              * 0    users:(("kylin-ai-vector",pid=3103,fd=8))                            
u_str LISTEN 0      50                                                                             /var/tmp/qtsingleapp-kylins-d447-3e8 14120              * 0    users:(("kylin-status-ma",pid=5104,fd=5))                            
u_str LISTEN 0      50                                                            /var/tmp/ukui-panel-config-kylin-agent-1000-wayland-0 20826              * 0    users:(("ukui-panel",pid=5905,fd=23))                                
u_str LISTEN 0      50                                                                           /var/tmp/ukui-idm-kylin-agentwayland-0 20362              * 0    users:(("peony-intellige",pid=7461,fd=18))                           
u_str LISTEN 0      50                                                                                 /tmp/qtsingleapp-kylinw-18db-3e8 31265              * 0    users:(("kylin-weather",pid=9971,fd=21))                             
u_str LISTEN 0      50                                                                             /var/tmp/qtsingleapp-kylinn-47e3-3e8 23227              * 0                                                                         
u_str LISTEN 0      50                                                                             /var/tmp/qtsingleapp-kylind-85ec-3e8 21339              * 0    users:(("kylin-device-da",pid=9523,fd=23))                           
u_str LISTEN 0      50                                                                             /var/tmp/qtsingleapp-kylinv-f0a2-3e8 28757              * 0    users:(("kylin-virtual-k",pid=9625,fd=21))                           
u_str LISTEN 0      4096                                                                       /home/kylin-agent/.kylinbot/gateway.sock 25068              * 0    users:(("kylin-bot",pid=9500,fd=12))                                 
u_str LISTEN 0      1                                                                                                 /tmp/.X11-unix/X0 15024              * 0    users:(("Xwayland",pid=5352,fd=27),("kylin-wlcom",pid=4868,fd=27))   
u_str LISTEN 0      10                                                                     /tmp/.kylin-ai-runtime-unix/1000/config.sock 28742              * 0    users:(("kylin-ai-runtim",pid=9434,fd=93))                           
u_str LISTEN 0      10                                                                      /var/run/lightdm/kylin-agent/greeter-socket 14447              * 0                                                                         
u_str LISTEN 0      10                                                                  /tmp/.kylin-ai-runtime-unix/1000/assistant.sock 26144              * 0    users:(("kylin-ai-runtim",pid=9434,fd=94))                           
u_str LISTEN 0      10                                                                  /tmp/.kylin-ai-runtime-unix/1000/genai-nlp.sock 21385              * 0    users:(("kylin-ai-runtim",pid=9434,fd=96))                           
u_str LISTEN 0      10                                                               /tmp/.kylin-ai-runtime-unix/1000/genai-vision.sock 26145              * 0    users:(("kylin-ai-runtim",pid=9434,fd=98))                           
u_str LISTEN 0      10                                                         /tmp/.kylin-ai-runtime-unix/1000/core-textembedding.sock 28743              * 0    users:(("kylin-ai-runtim",pid=9434,fd=101))                          
u_str LISTEN 0      10                                                                /tmp/.kylin-ai-runtime-unix/1000/core-speech.sock 26146              * 0    users:(("kylin-ai-runtim",pid=9434,fd=102))                          
u_str LISTEN 0      10                                                                /tmp/.kylin-ai-runtime-unix/1000/core-vision.sock 27712              * 0    users:(("kylin-ai-runtim",pid=9434,fd=104))                          
u_str LISTEN 0      50                                                   /var/tmp/ukui-search-service-monitor-kylin-agent1000-wayland-0 31814              * 0    users:(("ukui-search-ser",pid=10087,fd=25))                          
u_str LISTEN 0      10                                                        /tmp/.kylin-ai-runtime-unix/1000/core-imageembedding.sock 25135              * 0    users:(("kylin-ai-runtim",pid=9434,fd=106))                          
u_str LISTEN 0      50                                                                                 /tmp/qtsingleapp-KylinN-7497-3e8 31950              * 0    users:(("kylin-note",pid=9969,fd=22))                                
u_str LISTEN 0      50                                                                                 /tmp/qtsingleapp-aiassi-3d05-3e8 31997              * 0    users:(("kylin-aiassista",pid=9970,fd=23))                           
u_dgr UNCONN 0      0                                                                                                                 * 14990              * 0    users:(("kylin-wlcom-wra",pid=4408,fd=7))                            
u_str LISTEN 0      10                                                           @/tmp/.kylin-ai-business-unix/1000/DataManagement.sock 14559              * 0    users:(("kyai-data-manag",pid=3094,fd=4))                            
u_str LISTEN 0      1                                                                                                @/tmp/.X11-unix/X0 15023              * 0    users:(("Xwayland",pid=5352,fd=23),("kylin-wlcom",pid=4868,fd=23))   
u_str LISTEN 0      10                                                            @/tmp/.kylin-ai-business-unix/1000/Knowledgebase.sock 9098               * 0    users:(("kylin-ai-docume",pid=3098,fd=4))                            
u_str LISTEN 0      10                                                     @/tmp/.kylin-ai-business-unix/1000/KnowledgeBaseService.sock 14562              * 0    users:(("kylin-ai-knowle",pid=3100,fd=4))
```

## echo_service_status
```
# exit=0
Unit kylin-memory-echo.service could not be found.
```

## processes
```
# exit=0
   3107 /home/kylin-agent/d4d-venv/bin/python /home/kylin-agent/kylinOS-agent-memory/memory-service/app.py --socket /run/user/1000/kylin-memory/memory.sock
   5902 /usr/bin/xembed-sni-proxy
 329274 bash -c ps -u kylin-agent -o pid,cmd --no-headers 2>/dev/null | grep -iE 'echo|embed|memory' || echo NO_RELEVANT_PROCESS
 329276 grep -iE echo|embed|memory
```

## deploy_dir
```
# exit=0
总计 44
drwxrwxr-x  4 kylin-agent kylin-agent 4096  8月20日 22:35 .
drwx------ 33 kylin-agent kylin-agent 4096  8月24日 15:34 ..
drwxrwxr-x  2 kylin-agent kylin-agent 4096  8月20日 22:35 evaluation
drwxrwxr-x  9 kylin-agent kylin-agent 4096  8月20日 22:32 memory-service
-rw-rw-r--  1 kylin-agent kylin-agent 4736  8月20日 22:35 README.md
```
