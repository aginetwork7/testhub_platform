# -*- coding: utf-8 -*-
import time

GET_PARAMS = {
    "user_customers": {
        "name": "",
        "page.total": "",
        "page.limit": 1,
        "page.offset": 0
    }
}

POST_PARAMS = {
    "auth_login": {
        "email": "dingkangtest@gmail.com",
        "password": "34765f17aaad81f3a8c1682814edad9b119e875c25a2891c2b4aabc66b84f0e4"
    },

    "user_dealers": {
        "email": "apitest@dealer.com"
    },

    "id_ids_cars_search": {
        "brand": "",
        "color": "",
        "dateTimestamp": "",  # 动态设置
        "lpn": "",
        "model": "",
        "paging": {
            "limit": 20,
            "offset": 0
        }
    },

    "id_ids_edit": {
        "value": ""  # 动态设置
    },

    "asset_tracking_unique_object_relate": {
        "recordId": "",  # 动态设置
        "uniqueObjectId": ""  # 动态设置
    },

    "user_customers": {
        "accountName": "apitest_dealer_add_customer",
        "company": {
            "name": "test_add_customer"
        },
        "email": "apitest_add_customer@test.com",
        "firstName": "api",
        "lastName": "test",
        "phoneNumber": "12366787267"
    },

    "site_sites": {
        "site": {
            "details": {
                "address": "Cvojppmql Rdhndrj Kyhwglny Gstx TEST ADDRESS",
                "city": "TEST CITY",
                "state": "knvi TEST state",
                "zipcode": "6254362",
                "polygon": [
                    {
                        "latitude": 39.9526,
                        "longitude": -75.1652
                    }
                ]
            },
            "name": "api test site NAME"
        }
    },
    "org_users": {
        "email": "apitest_add_org_user@test.com",
        "firstName": "org api",
        "lastName": "org test",
        "phoneNumber": "123666667888",
        "roleName": "contact_user"
    },
    "virtual_guard_instruction": {
        "data": {
            "name": "test_virtual_guard_template_1",
            "id": "",
            "voice": "alloy",
            "workflows": [],
            "schedule": {
                "allYear": True,
                "allDay": True,
                "timeRanges": [],
                "weekdays": [
                    "sunday",
                    "monday",
                    "tuesday",
                    "wednesday",
                    "thursday",
                    "friday",
                    "saturday"
                ]
            }
        }
    }
}

PUT_PARAMS = {

}

DELETE_PARAMS = {

}

PATCH_PARAMS = {}

WEBSOCKET_PARAMS = {
    "send": {
        "request": {
            "id": "JHaxlU01PvZS5XeLN0VJkVP8vjRekL1",
            "act": "webrtc.user.device.connect",
            "data": {
            }
        },
        "headers": {
            "org_id": 126
        }
    },
    "action": {
        "alertUpdateCameraRule": "alert.update_camera_alert_rules",
        "alertUpdateCameraRuleReply": "alert.update_camera_alert_rules.reply",
        "cameraStatus": "device.camera_status",
        "destroy": "terminal.destroy",
        "deviceConnect": "webrtc.user.device.connect",
        "deviceConnectReply": "webrtc.user.device.connect.reply",
        "deviceEcho": "device.echo",
        "deviceEchoReply": "device.echo.reply",
        "deviceOnvifChange": "device.onvif.change",
        "deviceOnvifChangeReply": "device.onvif.change.reply",
        "deviceOpenRemoteService": "device.remote_service.open",
        "deviceOpenRemoteServiceReply": "device.remote_service.open.reply",
        "deviceReboot": "device.reboot",
        "deviceRefreshNvrCloudSettings": "device.refresh_nvr_cloud_settings",
        "deviceRefreshNvrCloudSettingsReply": "device.refresh_nvr_cloud_settings.reply",
        "deviceRemoteSsh": "device.remote_ssh",
        "deviceRemoteSshReply": "device.remote_ssh.reply",
        "deviceSearch": "device.search",
        "deviceSearchReply": "device.search.reply,backtouser",
        "deviceSearchReplyRes": "device.search.reply,devicetoserver",
        "deviceSpeakerAdd": "device.speaker.add",
        "deviceSpeakerAddReply": "device.speaker.add.reply",
        "deviceTakeSnapshots": "device.take_snapshots",
        "deviceTakeSnapshotsReply": "device.take_snapshots.reply",
        "deviceUpdateCamLocalSettings": "device.update_cam_local_settings",
        "deviceUpdateCamLocalSettingsReply": "device.update_cam_local_settings.reply",
        "deviceUpdateCamerasName": "device.update_cameras_name",
        "deviceUpdateCamerasNameReply": "device.update_cameras_name.reply",
        "deviceUpdateNvrLocalSettings": "device.update_nvr_local_settings",
        "deviceUpdateNvrLocalSettingsReply": "device.update_nvr_local_settings.reply",
        "deviceUpdateNvrTimezone": "device.update_nvr_timezone",
        "deviceUpdateNvrTimezoneReply": "device.update_nvr_timezone.reply",
        "deviceUpgrade": "device.upgrade",
        "deviceUpgradeReply": "device.upgrade.reply",
        "deviceUserCandidates": "webrtc.device.user.candidates",
        "deviceUserCandidatesReply": "webrtc.device.user.candidates.reply",
        "deviceValidate": "device.validate",
        "deviceValidateReply": "device.validate.reply,backtouser",
        "deviceValidateReplyRes": "device.validate.reply,devicetoserver",
        "deviceVersionUpgrade": "device.version_upgrade",
        "deviceVersionUpgradeReply": "device.version_upgrade.reply",
        "diskFormat": "device.DiskFormat",
        "diskFormatReply":"device.DiskFormatReply",
        "nvrStatus": "device.nvr_status",
        "nvrUpgrade": "device.nvr.upgrade",
        "nvrUpgradeReply": "device.nvr.upgrade.reply",
        "playbackGetRecords": "device.playback.get_records",
        "playbackGetRecordsReply": "device.playback.get_records.reply",
        "playbackGetRecordsReplyRes": "device.playback.get_records.reply",
        "speakerStatus": "device.speaker_status",
        "userDeviceCandidates": "webrtc.user.device.candidates",
        "userDeviceCandidatesReply": "webrtc.user.device.candidates.reply"
    },
    "deviceConnect":
        {
            "deviceConnect": {
                "credentialTurn": {
                    "urls": [
                        "turn:test-webrtc.agi7.ai:443"
                    ],
                    "username": "1729576971:user__140--dev__nvr_5000--conn__49dc13",
                    "credential": "iXvLk5+nLc3Rw0+T5BjVxk0A6cE="
                },
                "offer": "v=0\r\no=- 4145090755197190782 2 IN IP4 127.0.0.1\r\ns=-\r\nt=0 0\r\na=group:BUNDLE 0 1 2\r\na=extmap-allow-mixed\r\na=msid-semantic: WMS\r\nm=video 9 UDP/TLS/RTP/SAVPF 96 97 102 103 104 105 106 107 108 109 127 125 39 40 45 46 98 99 100 101 112 113 116 117 118\r\nc=IN IP4 0.0.0.0\r\na=rtcp:9 IN IP4 0.0.0.0\r\na=ice-ufrag:vWtT\r\na=ice-pwd:usXEOh7ehkUYG4BAXHOHyXGb\r\na=ice-options:trickle\r\na=fingerprint:sha-256 AC:C7:BC:7E:5B:E4:00:AC:63:66:26:C3:57:BB:7D:7A:8B:F7:C6:A0:78:08:87:D0:D2:FE:B6:EC:65:C7:7D:69\r\na=setup:actpass\r\na=mid:0\r\na=extmap:1 urn:ietf:params:rtp-hdrext:toffset\r\na=extmap:2 http://www.webrtc.org/experiments/rtp-hdrext/abs-send-time\r\na=extmap:3 urn:3gpp:video-orientation\r\na=extmap:4 http://www.ietf.org/id/draft-holmer-rmcat-transport-wide-cc-extensions-01\r\na=extmap:5 http://www.webrtc.org/experiments/rtp-hdrext/playout-delay\r\na=extmap:6 http://www.webrtc.org/experiments/rtp-hdrext/video-content-type\r\na=extmap:7 http://www.webrtc.org/experiments/rtp-hdrext/video-timing\r\na=extmap:8 http://www.webrtc.org/experiments/rtp-hdrext/color-space\r\na=extmap:9 urn:ietf:params:rtp-hdrext:sdes:mid\r\na=extmap:10 urn:ietf:params:rtp-hdrext:sdes:rtp-stream-id\r\na=extmap:11 urn:ietf:params:rtp-hdrext:sdes:repaired-rtp-stream-id\r\na=sendrecv\r\na=msid:- 5c410453-0060-42e5-81c1-551969d7a2cf\r\na=rtcp-mux\r\na=rtcp-rsize\r\na=rtpmap:96 VP8/90000\r\na=rtcp-fb:96 goog-remb\r\na=rtcp-fb:96 transport-cc\r\na=rtcp-fb:96 ccm fir\r\na=rtcp-fb:96 nack\r\na=rtcp-fb:96 nack pli\r\na=rtpmap:97 rtx/90000\r\na=fmtp:97 apt=96\r\na=rtpmap:102 H264/90000\r\na=rtcp-fb:102 goog-remb\r\na=rtcp-fb:102 transport-cc\r\na=rtcp-fb:102 ccm fir\r\na=rtcp-fb:102 nack\r\na=rtcp-fb:102 nack pli\r\na=fmtp:102 level-asymmetry-allowed=1;packetization-mode=1;profile-level-id=42001f\r\na=rtpmap:103 rtx/90000\r\na=fmtp:103 apt=102\r\na=rtpmap:104 H264/90000\r\na=rtcp-fb:104 goog-remb\r\na=rtcp-fb:104 transport-cc\r\na=rtcp-fb:104 ccm fir\r\na=rtcp-fb:104 nack\r\na=rtcp-fb:104 nack pli\r\na=fmtp:104 level-asymmetry-allowed=1;packetization-mode=0;profile-level-id=42001f\r\na=rtpmap:105 rtx/90000\r\na=fmtp:105 apt=104\r\na=rtpmap:106 H264/90000\r\na=rtcp-fb:106 goog-remb\r\na=rtcp-fb:106 transport-cc\r\na=rtcp-fb:106 ccm fir\r\na=rtcp-fb:106 nack\r\na=rtcp-fb:106 nack pli\r\na=fmtp:106 level-asymmetry-allowed=1;packetization-mode=1;profile-level-id=42e01f\r\na=rtpmap:107 rtx/90000\r\na=fmtp:107 apt=106\r\na=rtpmap:108 H264/90000\r\na=rtcp-fb:108 goog-remb\r\na=rtcp-fb:108 transport-cc\r\na=rtcp-fb:108 ccm fir\r\na=rtcp-fb:108 nack\r\na=rtcp-fb:108 nack pli\r\na=fmtp:108 level-asymmetry-allowed=1;packetization-mode=0;profile-level-id=42e01f\r\na=rtpmap:109 rtx/90000\r\na=fmtp:109 apt=108\r\na=rtpmap:127 H264/90000\r\na=rtcp-fb:127 goog-remb\r\na=rtcp-fb:127 transport-cc\r\na=rtcp-fb:127 ccm fir\r\na=rtcp-fb:127 nack\r\na=rtcp-fb:127 nack pli\r\na=fmtp:127 level-asymmetry-allowed=1;packetization-mode=1;profile-level-id=4d001f\r\na=rtpmap:125 rtx/90000\r\na=fmtp:125 apt=127\r\na=rtpmap:39 H264/90000\r\na=rtcp-fb:39 goog-remb\r\na=rtcp-fb:39 transport-cc\r\na=rtcp-fb:39 ccm fir\r\na=rtcp-fb:39 nack\r\na=rtcp-fb:39 nack pli\r\na=fmtp:39 level-asymmetry-allowed=1;packetization-mode=0;profile-level-id=4d001f\r\na=rtpmap:40 rtx/90000\r\na=fmtp:40 apt=39\r\na=rtpmap:45 AV1/90000\r\na=rtcp-fb:45 goog-remb\r\na=rtcp-fb:45 transport-cc\r\na=rtcp-fb:45 ccm fir\r\na=rtcp-fb:45 nack\r\na=rtcp-fb:45 nack pli\r\na=fmtp:45 level-idx=5;profile=0;tier=0\r\na=rtpmap:46 rtx/90000\r\na=fmtp:46 apt=45\r\na=rtpmap:98 VP9/90000\r\na=rtcp-fb:98 goog-remb\r\na=rtcp-fb:98 transport-cc\r\na=rtcp-fb:98 ccm fir\r\na=rtcp-fb:98 nack\r\na=rtcp-fb:98 nack pli\r\na=fmtp:98 profile-id=0\r\na=rtpmap:99 rtx/90000\r\na=fmtp:99 apt=98\r\na=rtpmap:100 VP9/90000\r\na=rtcp-fb:100 goog-remb\r\na=rtcp-fb:100 transport-cc\r\na=rtcp-fb:100 ccm fir\r\na=rtcp-fb:100 nack\r\na=rtcp-fb:100 nack pli\r\na=fmtp:100 profile-id=2\r\na=rtpmap:101 rtx/90000\r\na=fmtp:101 apt=100\r\na=rtpmap:112 H264/90000\r\na=rtcp-fb:112 goog-remb\r\na=rtcp-fb:112 transport-cc\r\na=rtcp-fb:112 ccm fir\r\na=rtcp-fb:112 nack\r\na=rtcp-fb:112 nack pli\r\na=fmtp:112 level-asymmetry-allowed=1;packetization-mode=1;profile-level-id=64001f\r\na=rtpmap:113 rtx/90000\r\na=fmtp:113 apt=112\r\na=rtpmap:116 red/90000\r\na=rtpmap:117 rtx/90000\r\na=fmtp:117 apt=116\r\na=rtpmap:118 ulpfec/90000\r\na=ssrc-group:FID 3080375312 2292016904\r\na=ssrc:3080375312 cname:I1207Ebz4battA5y\r\na=ssrc:3080375312 msid:- 5c410453-0060-42e5-81c1-551969d7a2cf\r\na=ssrc:2292016904 cname:I1207Ebz4battA5y\r\na=ssrc:2292016904 msid:- 5c410453-0060-42e5-81c1-551969d7a2cf\r\nm=audio 9 UDP/TLS/RTP/SAVPF 111 63 9 0 8 13 110 126\r\nc=IN IP4 0.0.0.0\r\na=rtcp:9 IN IP4 0.0.0.0\r\na=ice-ufrag:vWtT\r\na=ice-pwd:usXEOh7ehkUYG4BAXHOHyXGb\r\na=ice-options:trickle\r\na=fingerprint:sha-256 AC:C7:BC:7E:5B:E4:00:AC:63:66:26:C3:57:BB:7D:7A:8B:F7:C6:A0:78:08:87:D0:D2:FE:B6:EC:65:C7:7D:69\r\na=setup:actpass\r\na=mid:1\r\na=extmap:14 urn:ietf:params:rtp-hdrext:ssrc-audio-level\r\na=extmap:2 http://www.webrtc.org/experiments/rtp-hdrext/abs-send-time\r\na=extmap:4 http://www.ietf.org/id/draft-holmer-rmcat-transport-wide-cc-extensions-01\r\na=extmap:9 urn:ietf:params:rtp-hdrext:sdes:mid\r\na=sendrecv\r\na=msid:- c54428ec-9b26-428b-99a4-2f6128bb5e6d\r\na=rtcp-mux\r\na=rtcp-rsize\r\na=rtpmap:111 opus/48000/2\r\na=rtcp-fb:111 transport-cc\r\na=fmtp:111 minptime=10;useinbandfec=1\r\na=rtpmap:63 red/48000/2\r\na=fmtp:63 111/111\r\na=rtpmap:9 G722/8000\r\na=rtpmap:0 PCMU/8000\r\na=rtpmap:8 PCMA/8000\r\na=rtpmap:13 CN/8000\r\na=rtpmap:110 telephone-event/48000\r\na=rtpmap:126 telephone-event/8000\r\na=ssrc:68312386 cname:I1207Ebz4battA5y\r\na=ssrc:68312386 msid:- c54428ec-9b26-428b-99a4-2f6128bb5e6d\r\nm=application 9 UDP/DTLS/SCTP webrtc-datachannel\r\nc=IN IP4 0.0.0.0\r\na=ice-ufrag:vWtT\r\na=ice-pwd:usXEOh7ehkUYG4BAXHOHyXGb\r\na=ice-options:trickle\r\na=fingerprint:sha-256 AC:C7:BC:7E:5B:E4:00:AC:63:66:26:C3:57:BB:7D:7A:8B:F7:C6:A0:78:08:87:D0:D2:FE:B6:EC:65:C7:7D:69\r\na=setup:actpass\r\na=mid:2\r\na=sctp-port:5000\r\na=max-message-size:262144\r\n",
                "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJkZXZpY2VJZCI6Im52cl81MDAwIiwiZXhwIjoxNzI5NTc2OTcxLCJzZXNzaW9uSWQiOiJ1c2VyXzE0MDphNGY5ZTQwMC00MjAxLTQyMmEtYmEyNi1kY2ExNDQ0OWRjMTMiLCJ0eXBlIjoibnZyIiwidXNlcklkIjoxNDB9.2Jks_7CakQtcUgfaeV1Z4Ri37u9PHa2L8a4RbiZby0M",
                "type": "data",
                "connectId": "JHaxlU01PvZS5XeLN0VJkVP8vjRekL1"}
        },
    "alertUpdateCameraRule":
        {
            "alertUpdateCameraRule": {
                "data": [
                    {
                        "cameraId": "xxxx",
                        "remoteIndex": 1,
                        "algorithms": [
                            {
                                "algo": "intrusion",
                                "detections": [
                                    {
                                        "objects": [
                                            {
                                                "type": "non_motor_vehicle",
                                                "minDetectionWidth": 1000,
                                                "minDetectionHeight": 1000
                                            },
                                            {
                                                "type": "person",
                                                "minDetectionWidth": 120,
                                                "minDetectionHeight": 120
                                            },
                                            {
                                                "type": "vehicle",
                                                "minDetectionWidth": 560,
                                                "minDetectionHeight": 560
                                            }
                                        ],
                                        "region": {
                                            "type": "polygon",
                                            "polygon": {
                                                "points": [
                                                    {
                                                        "x": 46,
                                                        "y": 130
                                                    },
                                                    {
                                                        "x": 22,
                                                        "y": 9919
                                                    },
                                                    {
                                                        "x": 2663,
                                                        "y": 9919
                                                    },
                                                    {
                                                        "x": 2567,
                                                        "y": 151
                                                    }
                                                ],
                                                "sensitivity": 100,
                                                "timeThreshold": 1
                                            }
                                        },
                                        "index": 0
                                    },
                                    {
                                        "objects": [
                                            {
                                                "type": "person",
                                                "minDetectionWidth": 120,
                                                "minDetectionHeight": 120
                                            }
                                        ],
                                        "region": {
                                            "type": "polygon",
                                            "polygon": {
                                                "points": [
                                                    {
                                                        "x": 2376,
                                                        "y": 67
                                                    },
                                                    {
                                                        "x": 2448,
                                                        "y": 9940
                                                    },
                                                    {
                                                        "x": 4957,
                                                        "y": 9898
                                                    },
                                                    {
                                                        "x": 4909,
                                                        "y": 67
                                                    }
                                                ],
                                                "sensitivity": 40,
                                                "timeThreshold": 2
                                            }
                                        },
                                        "index": 1
                                    },
                                    {
                                        "objects": [
                                            {
                                                "type": "person",
                                                "minDetectionWidth": 120,
                                                "minDetectionHeight": 120
                                            },
                                            {
                                                "type": "vehicle",
                                                "minDetectionWidth": 560,
                                                "minDetectionHeight": 560
                                            }
                                        ],
                                        "region": {
                                            "type": "polygon",
                                            "polygon": {
                                                "points": [
                                                    {
                                                        "x": 5016,
                                                        "y": 24
                                                    },
                                                    {
                                                        "x": 5028,
                                                        "y": 9877
                                                    },
                                                    {
                                                        "x": 7896,
                                                        "y": 9856
                                                    },
                                                    {
                                                        "x": 7860,
                                                        "y": 24
                                                    }
                                                ],
                                                "sensitivity": 60,
                                                "timeThreshold": 6
                                            }
                                        },
                                        "index": 2
                                    },
                                    {
                                        "objects": [
                                            {
                                                "type": "non_motor_vehicle",
                                                "minDetectionWidth": 1000,
                                                "minDetectionHeight": 1000
                                            },
                                            {
                                                "type": "person",
                                                "minDetectionWidth": 120,
                                                "minDetectionHeight": 120
                                            },
                                            {
                                                "type": "vehicle",
                                                "minDetectionWidth": 560,
                                                "minDetectionHeight": 560
                                            }
                                        ],
                                        "region": {
                                            "type": "polygon",
                                            "polygon": {
                                                "points": [
                                                    {
                                                        "x": 7633,
                                                        "y": 45
                                                    },
                                                    {
                                                        "x": 7633,
                                                        "y": 9898
                                                    },
                                                    {
                                                        "x": 9951,
                                                        "y": 9834
                                                    },
                                                    {
                                                        "x": 9951,
                                                        "y": 88
                                                    }
                                                ],
                                                "sensitivity": 100,
                                                "timeThreshold": 10
                                            }
                                        },
                                        "index": 3
                                    }
                                ]
                            },
                            {
                                "algo": "cross_line",
                                "detections": [
                                    {
                                        "objects": [
                                            {
                                                "minDetectionHeight": 200,
                                                "minDetectionWidth": 200,
                                                "type": "person"
                                            },
                                            {
                                                "minDetectionHeight": 560,
                                                "minDetectionWidth": 560,
                                                "type": "vehicle"
                                            },
                                            {
                                                "minDetectionHeight": 1000,
                                                "minDetectionWidth": 1000,
                                                "type": "non_motor_vehicle"
                                            }
                                        ],
                                        "region": {
                                            "line": {
                                                "sensitivity": 100,
                                                "direction": "ab",
                                                "startPoint": {
                                                    "x": 918,
                                                    "y": 8147
                                                },
                                                "endPoint": {
                                                    "x": 978,
                                                    "y": 1164
                                                }
                                            },
                                            "type": "line"
                                        },
                                        "index": 0
                                    },
                                    {
                                        "objects": [
                                            {
                                                "minDetectionHeight": 200,
                                                "minDetectionWidth": 200,
                                                "type": "person"
                                            }
                                        ],
                                        "region": {
                                            "line": {
                                                "sensitivity": 20,
                                                "direction": "a_b",
                                                "startPoint": {
                                                    "x": 3368,
                                                    "y": 1037
                                                },
                                                "endPoint": {
                                                    "x": 3403,
                                                    "y": 9265
                                                }
                                            },
                                            "type": "line"
                                        },
                                        "index": 1
                                    },
                                    {
                                        "objects": [
                                            {
                                                "minDetectionHeight": 200,
                                                "minDetectionWidth": 200,
                                                "type": "person"
                                            },
                                            {
                                                "minDetectionHeight": 560,
                                                "minDetectionWidth": 560,
                                                "type": "vehicle"
                                            }
                                        ],
                                        "region": {
                                            "line": {
                                                "sensitivity": 60,
                                                "direction": "b_a",
                                                "startPoint": {
                                                    "x": 6115,
                                                    "y": 1185
                                                },
                                                "endPoint": {
                                                    "x": 6247,
                                                    "y": 9687
                                                }
                                            },
                                            "type": "line"
                                        },
                                        "index": 2
                                    },
                                    {
                                        "objects": [
                                            {
                                                "minDetectionHeight": 200,
                                                "minDetectionWidth": 200,
                                                "type": "person"
                                            },
                                            {
                                                "minDetectionHeight": 1000,
                                                "minDetectionWidth": 1000,
                                                "type": "non_motor_vehicle"
                                            }
                                        ],
                                        "region": {
                                            "line": {
                                                "sensitivity": 100,
                                                "direction": "ab",
                                                "startPoint": {
                                                    "x": 8529,
                                                    "y": 1311
                                                },
                                                "endPoint": {
                                                    "x": 8684,
                                                    "y": 9455
                                                }
                                            },
                                            "type": "line"
                                        },
                                        "index": 3
                                    }
                                ]
                            }
                        ],
                        "schedules": [
                            {
                                "allYear": False,
                                "allDay": False,
                                "timeRanges": [
                                    {
                                        "startedAt": 3600,
                                        "endedAt": 14400
                                    },
                                    {
                                        "startedAt": 18000,
                                        "endedAt": 28800
                                    },
                                    {
                                        "startedAt": 32400,
                                        "endedAt": 43200
                                    },
                                    {
                                        "startedAt": 46800,
                                        "endedAt": 57600
                                    }
                                ],
                                "weekdays": [
                                    "monday",
                                    "wednesday"
                                ]
                            },
                            {
                                "allDay": False,
                                "timeRanges": [
                                    {
                                        "startedAt": 7500,
                                        "endedAt": 25500
                                    },
                                    {
                                        "startedAt": 27300,
                                        "endedAt": 43500
                                    },
                                    {
                                        "startedAt": 45300,
                                        "endedAt": 61500
                                    },
                                    {
                                        "startedAt": 63300,
                                        "endedAt": 79500
                                    }
                                ],
                                "weekdays": [
                                    "tuesday",
                                    "thursday"
                                ],
                                "allYear": False
                            },
                            {
                                "allDay": False,
                                "timeRanges": [
                                    {
                                        "startedAt": 0,
                                        "endedAt": 43200
                                    },
                                    {
                                        "startedAt": 46500,
                                        "endedAt": 86400
                                    }
                                ],
                                "weekdays": [
                                    "friday"
                                ],
                                "allYear": False
                            },
                            {
                                "allDay": True,
                                "timeRanges": [],
                                "weekdays": [
                                    "saturday",
                                    "sunday"
                                ],
                                "allYear": False
                            }
                        ],
                        "actions": [
                            {
                                "notifiers": {
                                    "ownerNotifier": {
                                        "types": [
                                            "email"
                                        ]
                                    },
                                    "typedContacts": []
                                }
                            }
                        ],
                        "note": {
                            "types": [
                                "loitering"
                            ],
                            "note": "test note"
                        }
                    }
                ]
            }
        },

    "alertUpdateCameraRule_schedules":
        {
            "alertUpdateCameraRule": {
                "data": [
                    {
                        "cameraId": "xxxx",
                        "remoteIndex": 1,
                        "algorithms": [
                            {
                                "algo": "intrusion",
                                "detections": []
                            },
                            {
                                "algo": "cross_line",
                                "detections": []
                            }
                        ],
                        "schedules": [
                            {
                                "allYear": False,
                                "allDay": False,
                                "timeRanges": [
                                    {
                                        "startedAt": 3600,
                                        "endedAt": 14400
                                    },
                                    {
                                        "startedAt": 18000,
                                        "endedAt": 28800
                                    },
                                    {
                                        "startedAt": 32400,
                                        "endedAt": 43200
                                    },
                                    {
                                        "startedAt": 46800,
                                        "endedAt": 57600
                                    }
                                ],
                                "weekdays": [
                                    "monday",
                                    "wednesday"
                                ]
                            },
                            {
                                "allDay": False,
                                "timeRanges": [
                                    {
                                        "startedAt": 7500,
                                        "endedAt": 25500
                                    },
                                    {
                                        "startedAt": 27300,
                                        "endedAt": 43500
                                    },
                                    {
                                        "startedAt": 45300,
                                        "endedAt": 61500
                                    },
                                    {
                                        "startedAt": 63300,
                                        "endedAt": 79500
                                    }
                                ],
                                "weekdays": [
                                    "tuesday",
                                    "thursday"
                                ],
                                "allYear": False
                            },
                            {
                                "allDay": False,
                                "timeRanges": [
                                    {
                                        "startedAt": 0,
                                        "endedAt": 43200
                                    },
                                    {
                                        "startedAt": 46500,
                                        "endedAt": 86400
                                    }
                                ],
                                "weekdays": [
                                    "friday"
                                ],
                                "allYear": False
                            },
                            {
                                "allDay": True,
                                "timeRanges": [],
                                "weekdays": [
                                    "saturday",
                                    "sunday"
                                ],
                                "allYear": False
                            }
                        ],
                        "actions": [
                            {
                                "notifiers": {
                                    "ownerNotifier": {
                                        "types": []
                                    },
                                    "typedContacts": []
                                }
                            }
                        ],
                        "note": {
                            "types": [],
                            "note": ""
                        }
                    }
                ]
            }
        },

    "alertUpdateCameraRule_intrusion":
        {
            "alertUpdateCameraRule": {
                "data": [
                    {
                        "cameraId": "xxxx",
                        "remoteIndex": 1,
                        "algorithms": [
                            {
                                "algo": "intrusion",
                                "detections": [
                                    {
                                        "objects": [
                                            {
                                                "type": "non_motor_vehicle",
                                                "minDetectionWidth": 1000,
                                                "minDetectionHeight": 1000
                                            },
                                            {
                                                "type": "person",
                                                "minDetectionWidth": 120,
                                                "minDetectionHeight": 120
                                            },
                                            {
                                                "type": "vehicle",
                                                "minDetectionWidth": 560,
                                                "minDetectionHeight": 560
                                            }
                                        ],
                                        "region": {
                                            "type": "polygon",
                                            "polygon": {
                                                "points": [
                                                    {
                                                        "x": 46,
                                                        "y": 130
                                                    },
                                                    {
                                                        "x": 22,
                                                        "y": 9919
                                                    },
                                                    {
                                                        "x": 2663,
                                                        "y": 9919
                                                    },
                                                    {
                                                        "x": 2567,
                                                        "y": 151
                                                    }
                                                ],
                                                "sensitivity": 100,
                                                "timeThreshold": 1
                                            }
                                        },
                                        "index": 0
                                    },
                                    {
                                        "objects": [
                                            {
                                                "type": "person",
                                                "minDetectionWidth": 120,
                                                "minDetectionHeight": 120
                                            }
                                        ],
                                        "region": {
                                            "type": "polygon",
                                            "polygon": {
                                                "points": [
                                                    {
                                                        "x": 2376,
                                                        "y": 67
                                                    },
                                                    {
                                                        "x": 2448,
                                                        "y": 9940
                                                    },
                                                    {
                                                        "x": 4957,
                                                        "y": 9898
                                                    },
                                                    {
                                                        "x": 4909,
                                                        "y": 67
                                                    }
                                                ],
                                                "sensitivity": 40,
                                                "timeThreshold": 2
                                            }
                                        },
                                        "index": 1
                                    },
                                    {
                                        "objects": [
                                            {
                                                "type": "person",
                                                "minDetectionWidth": 120,
                                                "minDetectionHeight": 120
                                            },
                                            {
                                                "type": "vehicle",
                                                "minDetectionWidth": 560,
                                                "minDetectionHeight": 560
                                            }
                                        ],
                                        "region": {
                                            "type": "polygon",
                                            "polygon": {
                                                "points": [
                                                    {
                                                        "x": 5016,
                                                        "y": 24
                                                    },
                                                    {
                                                        "x": 5028,
                                                        "y": 9877
                                                    },
                                                    {
                                                        "x": 7896,
                                                        "y": 9856
                                                    },
                                                    {
                                                        "x": 7860,
                                                        "y": 24
                                                    }
                                                ],
                                                "sensitivity": 60,
                                                "timeThreshold": 6
                                            }
                                        },
                                        "index": 2
                                    },
                                    {
                                        "objects": [
                                            {
                                                "type": "non_motor_vehicle",
                                                "minDetectionWidth": 1000,
                                                "minDetectionHeight": 1000
                                            },
                                            {
                                                "type": "person",
                                                "minDetectionWidth": 120,
                                                "minDetectionHeight": 120
                                            },
                                            {
                                                "type": "vehicle",
                                                "minDetectionWidth": 560,
                                                "minDetectionHeight": 560
                                            }
                                        ],
                                        "region": {
                                            "type": "polygon",
                                            "polygon": {
                                                "points": [
                                                    {
                                                        "x": 7633,
                                                        "y": 45
                                                    },
                                                    {
                                                        "x": 7633,
                                                        "y": 9898
                                                    },
                                                    {
                                                        "x": 9951,
                                                        "y": 9834
                                                    },
                                                    {
                                                        "x": 9951,
                                                        "y": 88
                                                    }
                                                ],
                                                "sensitivity": 100,
                                                "timeThreshold": 10
                                            }
                                        },
                                        "index": 3
                                    }
                                ]
                            },
                            {
                                "algo": "cross_line",
                                "detections": []
                            }
                        ],
                        "schedules": [],
                        "actions": [
                            {
                                "notifiers": {
                                    "ownerNotifier": {
                                        "types": []
                                    },
                                    "typedContacts": []
                                }
                            }
                        ],
                        "note": {
                            "types": [],
                            "note": ""
                        }
                    }
                ]
            }
        },

    "alertUpdateCameraRule_crossline":
        {
            "alertUpdateCameraRule": {
                "data": [
                    {
                        "cameraId": "xxxx",
                        "remoteIndex": 1,
                        "algorithms": [
                            {
                                "algo": "intrusion",
                                "detections": []
                            },
                            {
                                "algo": "cross_line",
                                "detections": [
                                    {
                                        "objects": [
                                            {
                                                "minDetectionHeight": 200,
                                                "minDetectionWidth": 200,
                                                "type": "person"
                                            },
                                            {
                                                "minDetectionHeight": 560,
                                                "minDetectionWidth": 560,
                                                "type": "vehicle"
                                            },
                                            {
                                                "minDetectionHeight": 1000,
                                                "minDetectionWidth": 1000,
                                                "type": "non_motor_vehicle"
                                            }
                                        ],
                                        "region": {
                                            "line": {
                                                "sensitivity": 100,
                                                "direction": "ab",
                                                "startPoint": {
                                                    "x": 918,
                                                    "y": 8147
                                                },
                                                "endPoint": {
                                                    "x": 978,
                                                    "y": 1164
                                                }
                                            },
                                            "type": "line"
                                        },
                                        "index": 0
                                    },
                                    {
                                        "objects": [
                                            {
                                                "minDetectionHeight": 200,
                                                "minDetectionWidth": 200,
                                                "type": "person"
                                            }
                                        ],
                                        "region": {
                                            "line": {
                                                "sensitivity": 20,
                                                "direction": "a_b",
                                                "startPoint": {
                                                    "x": 3368,
                                                    "y": 1037
                                                },
                                                "endPoint": {
                                                    "x": 3403,
                                                    "y": 9265
                                                }
                                            },
                                            "type": "line"
                                        },
                                        "index": 1
                                    },
                                    {
                                        "objects": [
                                            {
                                                "minDetectionHeight": 200,
                                                "minDetectionWidth": 200,
                                                "type": "person"
                                            },
                                            {
                                                "minDetectionHeight": 560,
                                                "minDetectionWidth": 560,
                                                "type": "vehicle"
                                            }
                                        ],
                                        "region": {
                                            "line": {
                                                "sensitivity": 60,
                                                "direction": "b_a",
                                                "startPoint": {
                                                    "x": 6115,
                                                    "y": 1185
                                                },
                                                "endPoint": {
                                                    "x": 6247,
                                                    "y": 9687
                                                }
                                            },
                                            "type": "line"
                                        },
                                        "index": 2
                                    },
                                    {
                                        "objects": [
                                            {
                                                "minDetectionHeight": 200,
                                                "minDetectionWidth": 200,
                                                "type": "person"
                                            },
                                            {
                                                "minDetectionHeight": 1000,
                                                "minDetectionWidth": 1000,
                                                "type": "non_motor_vehicle"
                                            }
                                        ],
                                        "region": {
                                            "line": {
                                                "sensitivity": 100,
                                                "direction": "ab",
                                                "startPoint": {
                                                    "x": 8529,
                                                    "y": 1311
                                                },
                                                "endPoint": {
                                                    "x": 8684,
                                                    "y": 9455
                                                }
                                            },
                                            "type": "line"
                                        },
                                        "index": 3
                                    }
                                ]
                            }
                        ],
                        "schedules": [],
                        "actions": [
                            {
                                "notifiers": {
                                    "ownerNotifier": {
                                        "types": []
                                    },
                                    "typedContacts": []
                                }
                            }
                        ],
                        "note": {
                            "types": [],
                            "note": ""
                        }
                    }
                ]
            }
        },

    "alertUpdateCameraRule_other":
        {
            "alertUpdateCameraRule": {
                "data": [
                    {
                        "cameraId": "xxxx",
                        "remoteIndex": 1,
                        "algorithms": [
                            {
                                "algo": "intrusion",
                                "detections": []
                            },
                            {
                                "algo": "cross_line",
                                "detections": []
                            }
                        ],
                        "schedules": [
                            {
                                "allYear": False,
                                "allDay": False,
                                "timeRanges": [
                                    {
                                        "startedAt": 3600,
                                        "endedAt": 14400
                                    },
                                    {
                                        "startedAt": 18000,
                                        "endedAt": 28800
                                    },
                                    {
                                        "startedAt": 32400,
                                        "endedAt": 43200
                                    },
                                    {
                                        "startedAt": 46800,
                                        "endedAt": 57600
                                    }
                                ],
                                "weekdays": [
                                    "monday",
                                    "wednesday"
                                ]
                            },
                            {
                                "allDay": False,
                                "timeRanges": [
                                    {
                                        "startedAt": 7500,
                                        "endedAt": 25500
                                    },
                                    {
                                        "startedAt": 27300,
                                        "endedAt": 43500
                                    },
                                    {
                                        "startedAt": 45300,
                                        "endedAt": 61500
                                    },
                                    {
                                        "startedAt": 63300,
                                        "endedAt": 79500
                                    }
                                ],
                                "weekdays": [
                                    "tuesday",
                                    "thursday"
                                ],
                                "allYear": False
                            },
                            {
                                "allDay": False,
                                "timeRanges": [
                                    {
                                        "startedAt": 0,
                                        "endedAt": 43200
                                    },
                                    {
                                        "startedAt": 46500,
                                        "endedAt": 86400
                                    }
                                ],
                                "weekdays": [
                                    "friday"
                                ],
                                "allYear": False
                            },
                            {
                                "allDay": True,
                                "timeRanges": [],
                                "weekdays": [
                                    "saturday",
                                    "sunday"
                                ],
                                "allYear": False
                            }
                        ],
                        "actions": [
                            {
                                "notifiers": {
                                    "ownerNotifier": {
                                        "types": [
                                            "email"
                                        ]
                                    },
                                    "typedContacts": []
                                }
                            }
                        ],
                        "note": {
                            "types": [
                                "loitering"
                            ],
                            "note": "test note"
                        }
                    }
                ]
            }
        },

}

ALERT_PARAMS = {
    "person": {
        "event": {
            "tasks": [
                {
                    "id": "image_0",
                    "media": {
                        "ext": "jpeg",
                        "type": "image",
                        "meta": {
                            "type": 1
                        }
                    }
                },
                {
                    "id": "image_1",
                    "media": {
                        "ext": "jpeg",
                        "type": "image",
                        "meta": {
                            "type": 2
                        }
                    }
                },
                {
                    "id": "video_0",
                    "media": {
                        "ext": "mp4",
                        "type": "video",
                        "meta": {}
                    }
                }
            ],
            "meta": {
                "camera": {
                    "macAddress": "xxx",
                    "remoteIndex": 1
                },
                "uuid": "xxx"
            },
            "raw": {
                "alarm": {
                    "AlarmLevel": 0,
                    "AlarmSrcID": 3,
                    "AlarmSrcName": "",
                    "AlarmSrcType": 8,
                    "AlarmType": "SmartMotionDetectOn",
                    "RelatedID": "rk1YOHYnSfkzoph",
                    "TimeStamp": "xxx"
                },
                "struct": {
                    "RelatedID": "rk1YOHYnSfkzoph",
                    "SrcID": 3,
                    "SrcName": "xxx",
                    "StructureInfo": {
                        "ImageInfoList": [
                            {
                                "CaptureTime": "xxx",
                                "Format": 0,
                                "Height": 0,
                                "Index": 1,
                                "RealImageMeta": {
                                    "format": "jpeg",
                                    "height": 1520,
                                    "path": "/var/fs_disk/edgebox/image/8/3/rk1YOHYnSfkzoph_1.jpg",
                                    "size": 404576,
                                    "width": 2688
                                },
                                "Size": 400312,
                                "Type": 1,
                                "Width": 0
                            },
                            {
                                "CaptureTime": "xxx",
                                "Format": 0,
                                "Height": 0,
                                "Index": 2,
                                "RealImageMeta": {
                                    "format": "jpeg",
                                    "height": 448,
                                    "path": "/var/fs_disk/edgebox/image/8/3/rk1YOHYnSfkzoph_2.jpg",
                                    "size": 20894,
                                    "width": 256
                                },
                                "Size": 48564,
                                "Type": 2,
                                "Width": 0
                            }
                        ],
                        "ImageNum": 2,
                        "ObjInfo": {
                            "FaceInfoList": None,
                            "FaceNum": 0,
                            "FirePointsInfoList": None,
                            "FirePointsNum": 0,
                            "NonMotorVehicleInfoList": None,
                            "NonMotorVehicleNum": 0,
                            "PersonInfoList": [
                                {
                                    "AppearTime": "",
                                    "AttributeInfo": {
                                        "AgeRange": 98,
                                        "BagFlag": 98,
                                        "BodyToward": 0,
                                        "CoatColor": 2,
                                        "Gender": 98,
                                        "HairLength": 0,
                                        "ShoesTubeLength": 0,
                                        "SleevesLength": 0,
                                        "TrousersColor": 3,
                                        "TrousersLength": 0
                                    },
                                    "Confidence": 0,
                                    "DisAppearTime": "",
                                    "Feature": "",
                                    "FeatureVersion": "",
                                    "LargePicAttachIndex": 1,
                                    "PersonID": 1047,
                                    "Position": "2395,6450;3242,9196",
                                    "RuleInfo": {
                                        "PointList": None,
                                        "PointNum": 0,
                                        "RuleType": 5,
                                        "TriggerType": 0
                                    },
                                    "SmallPicAttachIndex": 2
                                }
                            ],
                            "PersonNum": 1,
                            "VehicleInfoList": None,
                            "VehicleNum": 0
                        }
                    },
                    "TimeStamp": "xxx"
                }
            }
        }
    },
    "snap_image": {
        "event": {
            "tasks": [
                {
                    "media": {
                        "meta": {
                            "index": 1,
                            "size": 404533,
                            "width": 2688,
                            "height": 1520,
                            "type": 1
                        }
                    },
                    "id": "image_0"
                },
                {
                    "media": {
                        "meta": {
                            "index": 2,
                            "size": 17215,
                            "width": 224,
                            "height": 448,
                            "type": 2
                        }
                    },
                    "id": "image_1"
                }
            ],
            "id": "xxx"
        }
    },
    "video_video": {
        "event": {
            "tasks": [
                {
                    "media": {
                        "meta": {
                            "size": 111503,
                            "startedAt": int(time.time()),
                            "endedAt": int(time.time()) + 10
                        }
                    },
                    "id": "video_0"
                }
            ],
            "id": "xxx"
        }
    },
    "vehicle": {
        "event": {
            "tasks": [
                {
                    "id": "image_0",
                    "media": {
                        "ext": "jpeg",
                        "type": "image",
                        "meta": {
                            "type": 1
                        }
                    }
                },
                {
                    "id": "image_1",
                    "media": {
                        "ext": "jpeg",
                        "type": "image",
                        "meta": {
                            "type": 2
                        }
                    }
                },
                {
                    "id": "video_0",
                    "media": {
                        "ext": "mp4",
                        "type": "video",
                        "meta": {}
                    }
                }
            ],
            "meta": {
                "camera": {
                    "macAddress": "xxx",
                    "remoteIndex": 1
                },
                "uuid": "xxx"
            },
            "raw": {
                "alarm": {
                    "AlarmLevel": 0,
                    "AlarmSrcID": 3,
                    "AlarmSrcName": "",
                    "AlarmSrcType": 8,
                    "AlarmType": "SmartMotionDetectOn",
                    "RelatedID": "rk1YOHYnSfkzoph",
                    "TimeStamp": "xxx"
                },
                "struct": {
                    "RelatedID": "rk1YOHYnSfkzoph",
                    "SrcID": 3,
                    "SrcName": "xxx",
                    "StructureInfo": {
                        "ImageInfoList": [
                            {
                                "CaptureTime": "xxx",
                                "Format": 0,
                                "Height": 0,
                                "Index": 1,
                                "RealImageMeta": {
                                    "format": "jpeg",
                                    "height": 1520,
                                    "path": "/var/fs_disk/edgebox/image/8/3/rk1YOHYnSfkzoph_1.jpg",
                                    "size": 404576,
                                    "width": 2688
                                },
                                "Size": 400312,
                                "Type": 1,
                                "Width": 0
                            },
                            {
                                "CaptureTime": "xxx",
                                "Format": 0,
                                "Height": 0,
                                "Index": 2,
                                "RealImageMeta": {
                                    "format": "jpeg",
                                    "height": 448,
                                    "path": "/var/fs_disk/edgebox/image/8/3/rk1YOHYnSfkzoph_2.jpg",
                                    "size": 20894,
                                    "width": 256
                                },
                                "Size": 48564,
                                "Type": 2,
                                "Width": 0
                            }
                        ],
                        "ImageNum": 2,
                        "ObjInfo": {
                            "FaceInfoList": None,
                            "FaceNum": 0,
                            "FirePointsInfoList": None,
                            "FirePointsNum": 0,
                            "NonMotorVehicleInfoList": None,
                            "NonMotorVehicleNum": 0,
                            "PersonInfoList": None,
                            "PersonNum": 0,
                            "VehicleInfoList": [
                                {
                                    "ID": 1,
                                    "Position": "3109,6136;5390,8266",
                                    "VehicleAttributeInfo": {
                                        "DriverSeatBeltStatus": "",
                                        "Type": 998,
                                        "VehicleBrand": "99",
                                        "AimStatus": "",
                                        "ImageDirection": 0,
                                        "Color": 100,
                                        "DriverMobileStatus": "",
                                        "DriverSunVisorStatus": "",
                                        "CodriverSunVisorStatus": "",
                                        "PendantStatus": "",
                                        "SpeedType": 0
                                    },
                                    "LargePicAttachIndex": 1,
                                    "Feature": "",
                                    "Confidence": 0,
                                    "DisAppearTime": "",
                                    "FeatureVersion": "",
                                    "AppearTime": "",
                                    "SmallPicAttachIndex": 2
                                }
                            ],
                            "VehicleNum": 1
                        }
                    },
                    "TimeStamp": "xxx"
                }
            }
        }
    }
}

