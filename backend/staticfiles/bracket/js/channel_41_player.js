(function () {
  const streamNode = document.getElementById("stream-url-data");
  const streamUrl = streamNode ? JSON.parse(streamNode.textContent) : "";
  const video = document.getElementById("channelPlayer");
  const statusEl = document.getElementById("playerStatus");
  const errorEl = document.getElementById("playerError");
  let mpegPlayer = null;
  let hlsPlayer = null;
  let stallTimer = null;

  function setError(message) {
    errorEl.textContent = message;
  }

  function clearError() {
    errorEl.textContent = "";
  }

  function setStatus(message) {
    statusEl.textContent = message;
  }

  function cleanupPlayers() {
    if (stallTimer) {
      window.clearTimeout(stallTimer);
      stallTimer = null;
    }

    if (hlsPlayer) {
      hlsPlayer.destroy();
      hlsPlayer = null;
    }

    if (mpegPlayer) {
      mpegPlayer.unload();
      mpegPlayer.detachMediaElement();
      mpegPlayer.destroy();
      mpegPlayer = null;
    }
  }

  async function safePlay() {
    try {
      await video.play();
      setStatus("Playing");
    } catch (_err) {
      setStatus("Autoplay blocked. Use the video play control.");
    }
  }

  function armStallTimer(onStall) {
    if (stallTimer) window.clearTimeout(stallTimer);
    stallTimer = window.setTimeout(function () {
      if (video.readyState < 2) {
        if (typeof onStall === "function") onStall();
      }
    }, 7000);
  }

  function isLikelyHls(url) {
    const lower = (url || "").toLowerCase();
    return lower.includes(".m3u8") || lower.includes("format=m3u8") || lower.includes("hls");
  }

  function startNativePlayback() {
    cleanupPlayers();
    video.src = streamUrl;
    setStatus("Starting native playback...");
    armStallTimer(function () {
      setError("Native playback stalled.");
      setStatus("");
    });
    safePlay();
  }

  function startHls(onFatal) {
    if (!(window.Hls && window.Hls.isSupported())) return false;

    cleanupPlayers();
    hlsPlayer = new window.Hls({
      lowLatencyMode: true,
      backBufferLength: 90,
    });
    setStatus("Starting HLS playback...");

    hlsPlayer.loadSource(streamUrl);
    hlsPlayer.attachMedia(video);
    hlsPlayer.on(window.Hls.Events.MANIFEST_PARSED, function () {
      armStallTimer(function () {
        if (typeof onFatal === "function") onFatal();
      });
      safePlay();
    });

    hlsPlayer.on(window.Hls.Events.ERROR, function (_event, data) {
      if (data && data.fatal) {
        if (typeof onFatal === "function") onFatal();
      }
    });

    return true;
  }

  function startMpegTs(onFatal) {
    const canUseMpegTs = window.mpegts && window.mpegts.getFeatureList && window.mpegts.getFeatureList().mseLivePlayback;
    if (!(canUseMpegTs && window.mpegts.isSupported())) return false;

    try {
      cleanupPlayers();
      mpegPlayer = window.mpegts.createPlayer(
        {
          type: "mpegts",
          isLive: true,
          url: streamUrl,
          hasAudio: false,
        },
        {
          lazyLoad: false,
          enableWorker: false,
          ignoreAudio: true,
          liveBufferLatencyChasing: true,
          liveSync: true,
        }
      );

      setStatus("Starting MPEG-TS playback...");
      mpegPlayer.attachMediaElement(video);
      mpegPlayer.load();
      armStallTimer(function () {
        if (typeof onFatal === "function") onFatal();
      });
      safePlay();

      mpegPlayer.on(window.mpegts.Events.ERROR, function () {
        if (typeof onFatal === "function") onFatal();
      });

      return true;
    } catch (_err) {
      if (typeof onFatal === "function") onFatal();
      return false;
    }
  }

  function startStream() {
    clearError();
    const likelyHls = isLikelyHls(streamUrl);

    if (video.canPlayType("application/vnd.apple.mpegurl") && likelyHls) {
      startNativePlayback();
      return;
    }

    if (likelyHls) {
      const hlsStarted = startHls(function () {
        setStatus("HLS failed, trying MPEG-TS...");
        const mpegStarted = startMpegTs(function () {
          setError("Stream error. HLS and MPEG-TS playback both failed.");
          setStatus("");
        });
        if (!mpegStarted) {
          setError("HLS failed and MPEG-TS is not supported in this browser.");
          setStatus("");
        }
      });

      if (!hlsStarted) {
        const mpegStarted = startMpegTs(function () {
          setError("Unable to initialize stream playback.");
          setStatus("");
        });
        if (!mpegStarted) {
          setError("This browser cannot play HLS or MPEG-TS for this stream.");
          setStatus("");
        }
      }
      return;
    }

    const mpegStarted = startMpegTs(function () {
      setStatus("MPEG-TS failed, trying HLS...");
      const hlsStarted = startHls(function () {
        setError("Stream error. MPEG-TS and HLS playback both failed.");
        setStatus("");
      });
      if (!hlsStarted) {
        setError("MPEG-TS failed and HLS is not supported in this browser.");
        setStatus("");
      }
    });

    if (!mpegStarted) {
      const hlsStarted = startHls(function () {
        setError("Unable to initialize stream playback.");
        setStatus("");
      });
      if (!hlsStarted) {
        setError("This browser cannot play this stream format directly.");
        setStatus("");
      }
    }
  }

  if (!streamUrl) {
    setError("No stream URL configured. Add HDHR_CHANNEL_41_URL or ?src=...");
    setStatus("");
    return;
  }

  video.addEventListener("loadeddata", function () {
    if (stallTimer) {
      window.clearTimeout(stallTimer);
      stallTimer = null;
    }
  });

  startStream();

  window.addEventListener("beforeunload", function () {
    cleanupPlayers();
  });
})();
