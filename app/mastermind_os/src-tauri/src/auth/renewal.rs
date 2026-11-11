//! Renewal admission belongs to the existing native authentication generation.
use super::*;

#[derive(Clone, PartialEq, Eq)]
pub(super) enum Renewal {
    Unadmitted,
    AccessOnly,
    Bound(String),
}
pub(super) struct RenewalTicket {
    pub(super) client: String,
    pub(super) generation: u64,
    pub(super) predecessor: String,
}
pub(super) struct RestoreTicket {
    pub(super) client: String,
    pub(super) generation: u64,
}

impl Inner {
    pub(super) fn renewal(&self, resource: Resource) -> Option<&Renewal> {
        match resource {
            Resource::Acquisition => Some(&self.acquisition_renewal),
            Resource::Content => Some(&self.content_renewal),
            Resource::Executive => None,
        }
    }
    pub(super) fn set_renewal(&mut self, resource: Resource, admission: Renewal) {
        match resource {
            Resource::Acquisition => self.acquisition_renewal = admission,
            Resource::Content => self.content_renewal = admission,
            Resource::Executive => (),
        }
    }
    pub(super) fn renewal_ticket(&self, resource: Resource) -> Result<RenewalTicket> {
        let Some(Renewal::Bound(predecessor)) = self.renewal(resource) else {
            return Err("AUTHENTICATION_REQUIRED".into());
        };
        Ok(RenewalTicket {
            client: self.client_id.clone().ok_or("NATIVE_CLIENT_ID_MISSING")?,
            generation: self.generation,
            predecessor: predecessor.clone(),
        })
    }
    pub(super) fn renewal_current(&self, resource: Resource, ticket: &RenewalTicket) -> bool {
        self.generation == ticket.generation && self.client_id.as_deref() == Some(ticket.client.as_str())
            && matches!(self.renewal(resource), Some(Renewal::Bound(value)) if *value == ticket.predecessor)
    }
    pub(super) fn retire_renewal(&mut self, resource: Resource, ticket: &RenewalTicket) {
        if self.renewal_current(resource, ticket) { self.set_renewal(resource, Renewal::Unadmitted); }
    }
    pub(super) fn begin_restore(&mut self) -> Option<RestoreTicket> {
        if self.restore_started || self.generation != 0 || self.pending.is_some() || self.exchanging
            || self.restoring || self.acquisition.is_some() || self.content.is_some() {
            return None;
        }
        let client = self.client_id.clone()?;
        self.restore_started = true;
        self.restoring = true;
        Some(RestoreTicket { client, generation: self.generation })
    }
    pub(super) fn restore_current(&self, ticket: &RestoreTicket) -> bool {
        self.restore_started && self.restoring && self.generation == ticket.generation
            && self.client_id.as_deref() == Some(ticket.client.as_str())
    }
    pub(super) fn admit_restored(&mut self, resource: Resource, ticket: &RestoreTicket, predecessor: String)
        -> Result<RenewalTicket>
    {
        if !self.restore_current(ticket) || self.renewal(resource) != Some(&Renewal::Unadmitted) {
            return Err("AUTHENTICATION_CHANGED".into());
        }
        self.set_renewal(resource, Renewal::Bound(predecessor));
        self.renewal_ticket(resource)
    }
    pub(super) fn finish_restore(&mut self, ticket: &RestoreTicket) -> bool {
        if !self.restore_current(ticket) { return false; }
        self.restoring = false;
        true
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn inner() -> Inner { Inner::with_executive_resource(Some("public-client"), None) }
    fn fingerprint(value: &str, resource: Resource) -> String {
        crate::native_refresh::fingerprint("public-client", resource.audience(), value)
    }
    #[test]
    fn access_only_expiry_or_token_removal_never_admits_stored_renewal() {
        let mut i = inner();
        for resource in [Resource::Acquisition, Resource::Content] {
            i.set_renewal(resource, Renewal::AccessOnly);
            assert!(i.renewal_ticket(resource).is_err());
            match resource { Resource::Acquisition => i.acquisition = None,
                Resource::Content => i.content = None, _ => () }
            assert!(i.renewal_ticket(resource).is_err());
        }
        assert!(i.renewal_ticket(Resource::Executive).is_err());
    }
    #[test]
    fn captured_ticket_refuses_foreign_replacement_and_does_not_retire_a_successor() {
        let mut i = inner(); let resource = Resource::Acquisition;
        let old = fingerprint("old-private-refresh-value", resource);
        i.set_renewal(resource, Renewal::Bound(old.clone()));
        let queued = i.renewal_ticket(resource).unwrap();
        assert!(i.renewal_current(resource, &queued));
        assert_ne!(queued.predecessor, fingerprint("foreign-private-refresh-value", resource));
        let next = fingerprint("new-successor-refresh-value", resource);
        i.set_renewal(resource, Renewal::Bound(next.clone()));
        assert!(!i.renewal_current(resource, &queued));
        i.retire_renewal(resource, &queued);
        assert!(i.renewal(resource) == Some(&Renewal::Bound(next)));
        i.begin_reauthentication();
        assert!(!i.renewal_current(resource, &queued));
        assert!(i.renewal_ticket(resource).is_err());
    }
    #[test]
    fn all_four_resource_combinations_keep_independent_renewal_authority() {
        for a in [false, true] { for c in [false, true] {
            let mut i = inner();
            for (resource, bound) in [(Resource::Acquisition, a), (Resource::Content, c)] {
                i.set_renewal(resource, if bound { Renewal::Bound(fingerprint("private-inert-refresh", resource)) }
                    else { Renewal::AccessOnly });
                assert_eq!(i.renewal_ticket(resource).is_ok(), bound);
            }
            assert_eq!(i.renewal_ticket(Resource::Acquisition).is_ok(), a);
            assert_eq!(i.renewal_ticket(Resource::Content).is_ok(), c);
        } }
    }
    #[test]
    fn startup_is_once_only_and_cannot_admit_content_or_clear_state_after_new_generation() {
        let mut i = inner(); let restore = i.begin_restore().unwrap();
        assert!(i.begin_restore().is_none());
        let a = i.admit_restored(Resource::Acquisition, &restore,
            fingerprint("inert-startup-predecessor", Resource::Acquisition)).unwrap();
        // No access token is required for a confirmed preconnect retry of the
        // same admitted predecessor. Missing access does not imply fresh adoption.
        assert!(i.acquisition.is_none() && i.renewal_current(Resource::Acquisition, &a));
        i.begin_reauthentication(); i.restoring = true;
        assert!(i.admit_restored(Resource::Content, &restore,
            fingerprint("foreign-content-refresh", Resource::Content)).is_err());
        assert!(!i.finish_restore(&restore)); assert!(i.restoring);
        assert!(i.begin_restore().is_none());
    }
    #[test]
    fn completed_startup_never_mints_another_restore_from_an_absent_token() {
        let mut i = inner(); let restore = i.begin_restore().unwrap();
        assert!(i.finish_restore(&restore)); assert!(!i.restoring);
        assert!(i.acquisition.is_none() && i.content.is_none());
        assert!(i.begin_restore().is_none());
        assert!(i.renewal_ticket(Resource::Acquisition).is_err());
    }
}
