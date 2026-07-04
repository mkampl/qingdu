package at.itvoodoo.qingdu;

import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {

    // BridgeActivity.load() already replays getIntent() through onNewIntent()
    // once, immediately after the bridge is created. On a cold launch from a
    // notification tap where the app's process had been killed in the
    // background (not force-stopped - that cancels the alarm entirely), that
    // first replay can land before the plugin stack is fully wired up and
    // the tap payload is silently dropped: the user lands on the default
    // route instead of the notification's deep link. Re-running it once
    // more from onStart (definitely after the bridge and its plugins have
    // finished initializing) is a no-op on every other launch path and
    // closes that gap for this one.
    @Override
    public void onStart() {
        super.onStart();
        if (this.bridge != null) {
            this.bridge.onNewIntent(getIntent());
        }
    }
}
