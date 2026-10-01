/* One real GET packet; mutate only the protocol fields under test. */
static const uint8_t request[] = {
  0x30,0x26,0x02,0x01,0x01,0x04,0x06,'p','u','b','l','i','c',
  0xa0,0x19,0x02,0x01,0x2a,0x02,0x01,0,0x02,0x01,0,
  0x30,0x0e,0x30,0x0c,0x06,0x08,0x2b,6,1,2,1,1,1,0,0x05,0
};
static int response_value(const uint8_t *response, int size, uint8_t *tag,
                          const uint8_t **value, int *length) {
  const uint8_t *p = response;
  int rem = size, len;
  assert(ber_tlv(&p,&rem,&len) == 0x30); rem = len;
  assert(ber_tlv(&p,&rem,&len) == 0x02); p+=len; rem-=len;
  assert(ber_tlv(&p,&rem,&len) == 0x04); p+=len; rem-=len;
  assert(ber_tlv(&p,&rem,&len) == 0xa2); rem=len;
  for (int i=0;i<3;i++) {
    assert(ber_tlv(&p,&rem,&len) == 0x02);
    assert(len == 1 && p[0] == (i == 0 ? 0x2a : 0));
    p+=len; rem-=len;
  }
  assert(ber_tlv(&p,&rem,&len) == 0x30); rem=len;
  assert(ber_tlv(&p,&rem,&len) == 0x30); rem=len;
  assert(ber_tlv(&p,&rem,&len) == 0x06); p+=len; rem-=len;
  *tag=(uint8_t)ber_tlv(&p,&rem,&len); *value=p; *length=len;
  return len;
}
int main(void) {
  uint8_t in[sizeof(request)], out[2048], tag;
  const uint8_t *val; int len;
  snmp_buffers_t buf;
  for (int version=0;version<2;version++) {
    memcpy(in,request,sizeof(in)); in[4]=(uint8_t)version;
    int n=process_pdu(in,sizeof(in),out,sizeof(out),"public",&buf);
    assert(n>0); response_value(out,n,&tag,&val,&len);
    assert(tag==4 && len==6 && !memcmp(val,"router",6));
    assert(process_pdu(in,sizeof(in),out,sizeof(out),"wrong",&buf)<0);
    assert(process_pdu(in,sizeof(in),out,sizeof(out),"",&buf)<0);
    in[13]=0xa3; /* SET must never produce a response. */
    assert(process_pdu(in,sizeof(in),out,sizeof(out),"public",&buf)<0);
    in[13]=0xa1; /* GETNEXT reaches the second fixture OID. */
    n=process_pdu(in,sizeof(in),out,sizeof(out),"public",&buf); assert(n>0);
    in[36]=5; /* GETNEXT beyond the last OID terminates a walk. */
    n=process_pdu(in,sizeof(in),out,sizeof(out),"public",&buf); assert(n>0);
    response_value(out,n,&tag,&val,&len); assert(len==0 && tag==(version ? 0x82 : 0x05));
    in[13]=0xa0; in[36]=9;
    n=process_pdu(in,sizeof(in),out,sizeof(out),"public",&buf); assert(n>0);
    response_value(out,n,&tag,&val,&len); assert(len==0 && tag==(version ? 0x80 : 0x05));
  }
  memcpy(in,request,sizeof(in));
  for (size_t size=0;size<sizeof(in);size++)
    assert(process_pdu(in,(int)size,out,sizeof(out),"public",&buf)<0);
  assert(process_pdu(in,sizeof(in),out,8,"public",&buf)<0);
  in[1]=0x82; in[2]=0xff; in[3]=0xff;
  assert(process_pdu(in,sizeof(in),out,sizeof(out),"public",&buf)<0);
  memset(test_value,'x',255); test_value[255]=0;
  memcpy(in,request,sizeof(in));
  int n=process_pdu(in,sizeof(in),out,sizeof(out),"public",&buf); assert(n>0);
  response_value(out,n,&tag,&val,&len); assert(tag==4 && len==255);
  puts("PASS: production SNMP v1/v2c GET/GETNEXT, SET rejection, communities, walk termination, truncation, oversized BER, output bounds and 255-byte strings");
  return 0;
}
